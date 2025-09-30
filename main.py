#!/usr/bin/env python3
"""
HidenCloud 多账号自动登录和续费脚本
支持多账号并发执行，每个账号使用独立代理
"""

import os
import sys
import time
import logging
import json
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

# =====================================================================
#                          日志配置
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# =====================================================================
#                       HidenCloud 自动登录类
# =====================================================================
class HidenCloudLogin:
    """HidenCloud 自动登录和续费主类"""
    
    def __init__(self, account_config: Dict):
        """初始化配置和运行结果收集器"""
        # 账号配置
        self.account_name = account_config.get('name', 'Unknown')
        self.cookie_value = account_config.get('cookie')
        self.email = account_config.get('email')
        self.password = account_config.get('password')
        self.proxy_config = account_config.get('proxy')  # 代理配置
        self.servers = account_config.get('servers', [])
        
        # 基础网站配置
        self.base_url = "https://dash.hidencloud.com"
        self.login_url = "https://dash.hidencloud.com/auth/login"
        
        # 验证配置
        self._validate_config()
        
        # 初始化运行结果收集器
        self.run_results = []
    
    def _validate_config(self):
        """验证配置完整性"""
        if not self.cookie_value and not (self.email and self.password):
            raise ValueError(f"账号 {self.account_name} 必须提供 cookie 或 email:password")
        
        if not self.servers:
            raise ValueError(f"账号 {self.account_name} 未配置服务器列表")
        
        logger.info(f"✅ 账号 {self.account_name} 配置验证通过")
    
    # =================================================================
    #                       主登录流程模块
    # =================================================================
    
    def process_all_servers(self, headless: bool = True) -> List[Dict]:
        """处理该账号下的所有服务器"""
        logger.info(f"🚀 开始处理账号: {self.account_name}")
        logger.info(f"📋 该账号有 {len(self.servers)} 个服务器需要处理")
        
        if self.proxy_config:
            logger.info(f"🌐 使用代理: {self.proxy_config.get('server', 'N/A')}")
        
        try:
            with sync_playwright() as p:
                # 启动浏览器（带代理配置）
                browser = self._launch_browser(p, headless)
                logger.info(f"✅ 账号 {self.account_name} 浏览器启动成功")
                
                # 创建浏览器上下文
                context = self._create_context(browser)
                logger.info(f"✅ 账号 {self.account_name} 浏览器上下文创建成功")
                
                # 创建页面实例
                page = context.new_page()
                logger.info(f"✅ 账号 {self.account_name} 页面实例创建成功")
                
                # 执行智能登录策略
                logger.info(f"🔐 账号 {self.account_name} 开始尝试登录...")
                
                # 策略1：优先尝试Cookie登录
                login_success = False
                if self._try_cookie_login(page):
                    logger.info(f"🎉 账号 {self.account_name} Cookie登录成功！")
                    login_success = True
                # 策略2：Cookie失败时尝试邮箱密码登录
                elif self._try_password_login(page):
                    logger.info(f"🎉 账号 {self.account_name} 邮箱密码登录成功！")
                    login_success = True
                else:
                    logger.error(f"❌ 账号 {self.account_name} 所有登录方式均失败")
                    return self.run_results
                
                if login_success:
                    # 处理所有服务器
                    for server in self.servers:
                        self._process_single_server(page, server)
                
                # 关闭浏览器
                browser.close()
                
        except Exception as e:
            logger.error(f"❌ 账号 {self.account_name} 处理过程中发生错误: {str(e)}")
        
        return self.run_results
    
    def _launch_browser(self, playwright, headless: bool) -> Browser:
        """启动浏览器（带代理配置）"""
        launch_options = {
            'headless': headless,
            'args': [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        }
        
        # 添加代理配置
        if self.proxy_config:
            proxy_dict = {
                'server': self.proxy_config['server']
            }
            if self.proxy_config.get('username'):
                proxy_dict['username'] = self.proxy_config['username']
            if self.proxy_config.get('password'):
                proxy_dict['password'] = self.proxy_config['password']
            
            launch_options['proxy'] = proxy_dict
            logger.info(f"🌐 账号 {self.account_name} 配置代理: {proxy_dict['server']}")
        
        return playwright.chromium.launch(**launch_options)
    
    def _create_context(self, browser: Browser) -> BrowserContext:
        """创建浏览器上下文"""
        return browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
    
    # =================================================================
    #                       Cookie登录模块
    # =================================================================
    
    def _try_cookie_login(self, page: Page) -> bool:
        """Cookie 快速登录"""
        if not self.cookie_value:
            logger.info(f"⭐️ 账号 {self.account_name} 未提供 Cookie，跳过 Cookie 登录")
            return False
        
        logger.info(f"🪙 账号 {self.account_name} 开始尝试 Cookie 登录...")
        
        # 设置认证Cookie
        if not self._set_cookies(page):
            logger.error(f"❌ 账号 {self.account_name} Cookie 设置失败")
            return False
        
        # 访问dashboard验证登录
        try:
            logger.info(f"🌐 账号 {self.account_name} 正在验证Cookie有效性...")
            page.goto(f"{self.base_url}/dashboard", wait_until='networkidle', timeout=60000)
            
            # 验证登录状态
            if self._is_login_required(page):
                logger.warning(f"⚠️ 账号 {self.account_name} Cookie 已失效，需要重新登录")
                page.context.clear_cookies()
                return False
            
            logger.info(f"✅ 账号 {self.account_name} Cookie 登录成功！")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} Cookie 登录失败: {str(e)}")
            return False
    
    def _set_cookies(self, page: Page) -> bool:
        """设置登录 Cookie"""
        try:
            cookie = {
                "name": "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d",
                "value": self.cookie_value,
                "domain": "dash.hidencloud.com",
                "path": "/",
                "expires": int(time.time()) + 3600 * 24 * 365,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax"
            }
            
            page.context.add_cookies([cookie])
            logger.info(f"✅ 账号 {self.account_name} Cookie 设置完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 账号 {self.account_name} Cookie 设置失败: {str(e)}")
            return False
    
    # =================================================================
    #                       邮箱密码登录模块
    # =================================================================
    
    def _try_password_login(self, page: Page) -> bool:
        """邮箱密码登录"""
        if not (self.email and self.password):
            logger.error(f"❌ 账号 {self.account_name} 未提供邮箱密码，无法执行密码登录")
            return False
        
        logger.info(f"🔧 账号 {self.account_name} 开始尝试邮箱密码登录...")
        
        try:
            # 访问登录页面
            logger.info(f"🌐 账号 {self.account_name} 正在访问登录页面...")
            page.goto(self.login_url, wait_until="networkidle", timeout=60000)
            
            # 填写登录表单
            logger.info(f"📝 账号 {self.account_name} 正在填写登录信息...")
            page.fill('input[name="email"]', self.email)
            page.fill('input[name="password"]', self.password)
            
            # 处理 Cloudflare 验证
            self._handle_cloudflare_verification(page)
            
            # 提交登录表单
            logger.info(f"🚀 账号 {self.account_name} 正在提交登录表单...")
            page.click('button[type="submit"]:has-text("Sign in to your account")')
            
            # 等待登录完成并跳转
            page.wait_for_url(f"{self.base_url}/dashboard", timeout=60000)
            logger.info(f"✅ 账号 {self.account_name} 成功跳转到控制面板")
            
            # 验证登录状态
            if self._is_login_required(page):
                logger.error(f"❌ 账号 {self.account_name} 登录验证失败，请检查账号密码")
                return False
            
            logger.info(f"✅ 账号 {self.account_name} 邮箱密码登录验证成功！")
            return True
            
        except Exception as e:
            logger.error(f"❌ 账号 {self.account_name} 邮箱密码登录失败: {str(e)}")
            return False
    
    def _handle_cloudflare_verification(self, page: Page):
        """处理 Cloudflare Turnstile 验证"""
        logger.info(f"🔍 账号 {self.account_name} 检查是否存在 Cloudflare 验证...")
        
        try:
            turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            checkbox = turnstile_frame.locator('input[type="checkbox"]')
            
            checkbox.wait_for(state="visible", timeout=30000)
            checkbox.click()
            logger.info(f"✅ 账号 {self.account_name} 已点击Cloudflare验证复选框")
            
            page.wait_for_function(
                "() => document.querySelector('[name=\"cf-turnstile-response\"]') && document.querySelector('[name=\"cf-turnstile-response\"]').value",
                timeout=60000
            )
            logger.info(f"✅ 账号 {self.account_name} Cloudflare 验证通过完成")
            
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} Cloudflare 验证处理失败，继续尝试登录: {str(e)}")
    
    # =================================================================
    #                       单服务器处理模块
    # =================================================================
    
    def _process_single_server(self, page: Page, server: Dict):
        """处理单个服务器的续费"""
        server_url = server['url']
        server_id = server['id']
        server_name = server.get('name', f"服务器{server_id}")
        
        logger.info(f"📦 账号 {self.account_name} 开始处理服务器: {server_name} ({server_id})")
        
        # 初始化该服务器的运行结果
        result = {
            'account_name': self.account_name,
            'server_id': f"{server_name}({server_id})",
            'renewal_status': 'Unknown',
            'remaining_days': None,
            'old_due_date': None,
            'new_due_date': None,
            'start_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            # 访问服务器管理页面
            logger.info(f"🌐 账号 {self.account_name} 正在访问服务器: {server_url}")
            page.goto(server_url, wait_until='networkidle', timeout=60000)
            logger.info(f"✅ 账号 {self.account_name} 服务器页面加载完成")
            
            # 执行续费操作
            self._perform_renewal(page, result)
            
        except Exception as e:
            logger.error(f"❌ 账号 {self.account_name} 处理服务器 {server_name} 失败: {str(e)}")
            result['renewal_status'] = 'Failed'
        
        # 保存结果
        self.run_results.append(result)
    
    # =================================================================
    #                       续费功能模块
    # =================================================================
    
    def _perform_renewal(self, page: Page, result: Dict):
        """执行服务续费操作"""
        try:
            logger.info(f"🔄 账号 {self.account_name} 服务器 {result['server_id']} 开始执行续费操作...")
            
            # 步骤1：记录续费前的到期时间
            old_due_date = self._record_due_date(page, "续费前")
            result['old_due_date'] = old_due_date
            
            # 步骤2：查找并点击Renew按钮
            renew_button = page.locator('button:has-text("Renew")')
            renew_button.wait_for(state="visible", timeout=10000)
            
            if renew_button.is_enabled():
                logger.info(f"🎯 账号 {self.account_name} 找到Renew按钮，准备点击...")
                renew_button.click()
                logger.info(f"✅ 账号 {self.account_name} 已点击Renew按钮")
                
                # 步骤3：处理续费弹窗
                self._handle_renewal_dialog(page, result)
                
            else:
                logger.warning(f"⚠️ 账号 {self.account_name} Renew按钮存在但不可点击，可能服务不需要续费")
                result['renewal_status'] = 'NotNeeded'
                
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} 续费操作执行失败: {str(e)}")
            result['renewal_status'] = 'Failed'
    
    def _handle_renewal_dialog(self, page: Page, result: Dict):
        """处理续费相关弹窗"""
        try:
            logger.info(f"💬 账号 {self.account_name} 等待弹窗出现...")
            time.sleep(2)
            
            # 检查续费限制弹窗
            if self._check_renewal_restriction(page, result):
                logger.info(f"📋 账号 {self.account_name} 检测到续费限制弹窗，执行结果: 未到续期时间")
                return
            
            # 检查续费确认弹窗
            if self._check_renewal_confirmation(page, result):
                logger.info(f"📋 账号 {self.account_name} 检测到续费确认弹窗，开始执行续费流程")
                return
                
            # 未检测到预期弹窗
            logger.warning(f"⚠️ 账号 {self.account_name} 未检测到预期的弹窗")
                
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} 处理续费弹窗失败: {str(e)}")
    
    def _check_renewal_restriction(self, page: Page, result: Dict) -> bool:
        """检查续费限制弹窗"""
        try:
            restriction_title = page.locator('text="Renewal Restricted"')
            restriction_message = page.locator('p:has-text("You can only renew your free service when there is less than 1 day left before it expires")')
            
            if restriction_title.is_visible() and restriction_message.is_visible():
                try:
                    full_message = restriction_message.text_content().strip()
                    logger.info(f"📝 账号 {self.account_name} 限制说明: '{full_message}'")
                    
                    # 提取剩余天数
                    remaining_days = self._extract_remaining_days(full_message)
                    if remaining_days:
                        result['remaining_days'] = remaining_days
                        logger.info(f"📅 账号 {self.account_name} 剩余天数: {remaining_days}天")
                    
                except Exception as e:
                    logger.warning(f"⚠️ 账号 {self.account_name} 获取完整限制说明失败: {str(e)}")
                
                result['renewal_status'] = 'Unexpired'
                return True
                
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} 检查续费限制时出错: {str(e)}")
            
        return False
    
    def _check_renewal_confirmation(self, page: Page, result: Dict) -> bool:
        """检查续费确认弹窗并执行续费流程"""
        try:
            confirmation_title = page.locator('text="Renew Plan"')
            confirmation_message = page.locator('text="Below you can renew your service for another Week. After hitting "Renew", we will generate an invoice for you to pay."')
            
            if confirmation_title.is_visible() and confirmation_message.is_visible():
                logger.info(f"✅ 账号 {self.account_name} 确认为续费确认弹窗")
                
                # 点击Create Invoice按钮
                create_invoice_button = page.locator('button:has-text("Create Invoice")')
                
                if create_invoice_button.is_visible():
                    logger.info(f"🎯 账号 {self.account_name} 找到Create Invoice按钮，点击确认...")
                    create_invoice_button.click()
                    logger.info(f"✅ 账号 {self.account_name} Invoice创建请求已提交")
                    
                    # 处理Invoice页面和支付
                    self._handle_invoice_and_payment(page, result)
                    return True
                    
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} 检查续费确认时出错: {str(e)}")
            
        return False
    
    def _handle_invoice_and_payment(self, page: Page, result: Dict):
        """处理Invoice页面和支付流程"""
        try:
            logger.info(f"💳 账号 {self.account_name} 等待Invoice页面加载...")
            time.sleep(10)
            
            current_url = page.url
            is_invoice_url = "/payment/invoice/" in current_url
            
            success_text = page.locator('text="Success!"')
            invoice_text = page.locator('text="Invoice has been generated successfully"')
            pay_button = page.get_by_role("button", name="Pay", exact=True)
            
            if is_invoice_url and success_text.is_visible() and invoice_text.is_visible() and pay_button.is_visible():
                logger.info(f"✅ 账号 {self.account_name} 确认为Invoice页面，开始支付流程")
                
                pay_button.click()
                logger.info(f"✅ 账号 {self.account_name} 支付请求已提交")
                
                time.sleep(5)
                
                # 检查支付结果
                self._check_payment_result(page, result)
                
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} 处理Invoice和支付失败: {str(e)}")
    
    def _check_payment_result(self, page: Page, result: Dict):
        """检查支付完成状态"""
        try:
            logger.info(f"🔍 账号 {self.account_name} 等待支付处理完成...")
            
            page.wait_for_url("**/dashboard", timeout=15000)
            logger.info(f"✅ 账号 {self.account_name} 已跳转回Dashboard页面")
            
            result['renewal_status'] = 'Success'
            
            # 跳转回服务管理页面记录新的到期时间
            server_url = result.get('server_url')
            if server_url:
                page.goto(server_url, wait_until="networkidle", timeout=30000)
                new_due_date = self._record_due_date(page, "续费后")
                result['new_due_date'] = new_due_date
            
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} 支付结果检查失败: {str(e)}")
    
    # =================================================================
    #                       时间记录模块
    # =================================================================
    
    def _record_due_date(self, page: Page, stage: str) -> Optional[str]:
        """记录到期时间"""
        try:
            if stage == "续费后":
                time.sleep(2)
            
            due_date_label = page.locator('text="Due date"')
            if due_date_label.is_visible():
                parent_container = due_date_label.locator('..')
                date_text = parent_container.locator('text=/\\d{1,2}\\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d{4}/').first
                if date_text.is_visible():
                    due_date_raw = date_text.text_content().strip()
                    logger.info(f"📅 账号 {self.account_name} {stage}原始时间: {due_date_raw}")
                    
                    due_date_formatted = self._convert_date_format(due_date_raw)
                    return due_date_formatted
                    
        except Exception as e:
            logger.warning(f"⚠️ 账号 {self.account_name} 获取{stage}到期时间失败: {str(e)}")
            
        return None
    
    def _convert_date_format(self, date_str: str) -> str:
        """将网页日期格式转换为标准格式"""
        try:
            month_map = {
                'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
            }
            
            parts = date_str.strip().split()
            if len(parts) == 3:
                day = parts[0].zfill(2)
                month = month_map.get(parts[1], '00')
                year = parts[2]
                
                converted_date = f"{year}-{month}-{day}"
                return converted_date
            else:
                return date_str
                
        except Exception as e:
            logger.warning(f"⚠️ 日期格式转换失败: {str(e)}")
            return date_str
    
    # =================================================================
    #                       辅助工具模块
    # =================================================================
    
    def _extract_remaining_days(self, message: str) -> Optional[int]:
        """从限制说明中提取剩余天数"""
        try:
            import re
            pattern = r'expires in (\d+) days?'
            match = re.search(pattern, message, re.IGNORECASE)
            
            if match:
                return int(match.group(1))
            return None
                
        except Exception as e:
            logger.warning(f"⚠️ 提取剩余天数失败: {str(e)}")
            return None
    
    def _is_login_required(self, page: Page) -> bool:
        """检查是否需要登录"""
        return "/auth/login" in page.url


# =====================================================================
#                          配置加载模块
# =====================================================================

def load_accounts_config() -> List[Dict]:
    """加载多账号配置"""
    try:
        accounts_json = os.getenv('HIDENCLOUD_ACCOUNTS')
        if not accounts_json:
            raise ValueError("未设置环境变量 HIDENCLOUD_ACCOUNTS")
        
        accounts = json.loads(accounts_json)
        if not accounts:
            raise ValueError("账号配置为空")
        
        logger.info(f"✅ 成功加载 {len(accounts)} 个账号配置")
        return accounts
        
    except json.JSONDecodeError as e:
        raise ValueError(f"❌ 账号配置JSON解析失败: {str(e)}")
    except Exception as e:
        raise ValueError(f"❌ 加载账号配置失败: {str(e)}")


# =====================================================================
#                          报告生成模块
# =====================================================================

def generate_readme(all_results: List[Dict]):
    """生成README.md运行报告"""
    try:
        logger.info("📝 正在生成README.md文件...")
        
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        
        readme_content = f"""**最后运行时间**: `{current_time}`

**运行结果**: <br>

"""
        
        # 按账号分组显示结果
        account_groups = {}
        for result in all_results:
            account_name = result['account_name']
            if account_name not in account_groups:
                account_groups[account_name] = []
            account_groups[account_name].append(result)
        
        # 生成每个账号的结果
        for account_name, results in account_groups.items():
            readme_content += f"### 账号: {account_name}\n\n"
            
            for result in results:
                # 根据续费状态设置图标和状态文本
                if result['renewal_status'] == 'Success':
                    status_icon = '✅'
                    status_text = 'Success'
                elif result['renewal_status'] == 'Unexpired':
                    status_icon = 'ℹ️'
                    if result['remaining_days']:
                        status_text = f'Unexpired({result["remaining_days"]}天)'
                    else:
                        status_text = 'Unexpired'
                else:
                    status_icon = '❌'
                    status_text = result['renewal_status']
                
                readme_content += f"🖥️服务器ID：`{result['server_id']}`<br>\n"
                readme_content += f"📊续期结果：{status_icon}{status_text}<br>\n"
                readme_content += f"🕛️旧到期时间: `{result['old_due_date'] or 'N/A'}`<br>\n"
                
                # 续费成功时添加新到期时间
                if result['renewal_status'] == 'Success' and result['new_due_date']:
                    readme_content += f"🕡️新到期时间：`{result['new_due_date']}`<br>\n"
                
                readme_content += "\n"
            
            readme_content += "---\n\n"
        
        # 写入README.md文件
        with open('README.md', 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        logger.info("✅ README.md文件生成成功")
        
    except Exception as e:
        logger.warning(f"⚠️ 生成README.md失败: {str(e)}")


# =====================================================================
#                          主程序入口
# =====================================================================

def main():
    """主程序执行流程"""
    try:
        logger.info("🚀 开始执行 HidenCloud 多账号自动续费脚本...")
        
        # 步骤1：加载所有账号配置
        logger.info("📋 正在加载账号配置...")
        accounts_config = load_accounts_config()
        logger.info(f"✅ 成功加载 {len(accounts_config)} 个账号")
        
        # 步骤2：确定浏览器运行模式
        is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
        headless = is_github_actions or os.getenv('HEADLESS', 'true').lower() == 'true'
        
        if headless:
            logger.info("💻 使用无头模式运行（适合CI/CD环境）")
        else:
            logger.info("🖥️ 使用有界面模式运行（适合本地调试）")
        
        # 步骤3：并发处理所有账号
        all_results = []
        max_workers = min(len(accounts_config), 3)  # 最多3个并发，避免资源占用过高
        
        logger.info(f"🔄 开始并发处理账号（最大并发数: {max_workers}）...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 为每个账号创建处理任务
            future_to_account = {}
            for account_config in accounts_config:
                try:
                    client = HidenCloudLogin(account_config)
                    future = executor.submit(client.process_all_servers, headless)
                    future_to_account[future] = account_config.get('name', 'Unknown')
                except Exception as e:
                    logger.error(f"❌ 创建账号处理任务失败: {str(e)}")
            
            # 收集所有任务结果
            for future in as_completed(future_to_account):
                account_name = future_to_account[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    logger.info(f"✅ 账号 {account_name} 处理完成，共 {len(results)} 个服务器")
                except Exception as e:
                    logger.error(f"❌ 账号 {account_name} 处理失败: {str(e)}")
        
        # 步骤4：生成README.md报告
        logger.info("📝 开始生成运行报告...")
        generate_readme(all_results)
        
        # 步骤5：处理执行结果
        success_count = sum(1 for r in all_results if r['renewal_status'] in ['Success', 'Unexpired', 'NotNeeded'])
        total_count = len(all_results)
        
        logger.info(f"📊 任务完成统计: 成功/总数 = {success_count}/{total_count}")
        
        if success_count == total_count:
            logger.info("🎉 所有服务器处理成功！")
            sys.exit(0)
        elif success_count > 0:
            logger.warning(f"⚠️ 部分服务器处理失败: {total_count - success_count}/{total_count}")
            sys.exit(0)  # 部分成功也返回0，避免触发告警
        else:
            logger.error("❌ 所有服务器处理失败！")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"💥 脚本执行过程中发生严重错误: {str(e)}")
        sys.exit(1)


# =====================================================================
#                          程序启动点
# =====================================================================

if __name__ == "__main__":
    main()
