import re
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# UUID 正则：标准 8-4-4-4-12 格式
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def mask_uuid(text: str) -> str:
    """将文本中所有 UUID 脱敏，保留前8位，其余用 * 替代。"""
    def _mask(m: re.Match) -> str:
        s = m.group()
        return s[:8] + "-****-****-****-************"
    return UUID_PATTERN.sub(_mask, text)


@register(
    "astrbot_plugin_simpass-auth",
    "xinghanxu",
    "SimPass OTP 验证插件，使用 /sp-otp <id> <验证码> 进行身份验证",
    "1.0.0",
    "https://github.com/xinghanxu6666/astrbot_plugin_simpass-auth",
)
class SimpassOtpPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 兼容 AstrBot 未传入 config 的情况（_conf_schema.json 未被识别时）
        self.config = config if config is not None else {}

    @filter.command("sp-otp")
    async def sp_otp(self, event: AstrMessageEvent):
        """SimPass 身份验证指令。用法：/sp-otp <用户ID> <验证码>"""

        # 解析参数
        parts = event.message_str.strip().split()
        args = parts[1:]  # parts[0] 是指令本身

        if len(args) < 2:
            yield event.plain_result(
                "❌ 参数不足。\n用法：/sp-otp <用户ID> <验证码>\n示例：/sp-otp 12345 678901"
            )
            return

        user_id_str, verify_code_str = args[0], args[1]

        if not user_id_str.isdigit():
            yield event.plain_result("❌ 用户ID 必须为数字。")
            return
        if not verify_code_str.isdigit():
            yield event.plain_result("❌ 验证码必须为数字。")
            return

        user_id = int(user_id_str)
        verify_code = int(verify_code_str)

        # 从控制台配置读取参数
        dev_uuid: str = (self.config.get("dev_uuid") or "").strip()
        if not dev_uuid:
            yield event.plain_result(
                "❌ 插件尚未配置开发者 UUID，请在插件设置中填写 dev_uuid。"
            )
            return

        api_url: str = (self.config.get("api_url") or "").strip()
        if not api_url:
            yield event.plain_result(
                "❌ 插件尚未配置 API 地址，请在插件设置中填写 api_url。"
            )
            return

        logger.info(f"[SimpassOTP] 发起验证请求：user_id={user_id}")

        params = {
            "uuid": dev_uuid,
            "user_id": user_id,
            "verify_code": verify_code,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        yield event.plain_result(
                            f"❌ SimPass 服务器返回异常状态码：{resp.status}"
                        )
                        return
                    data: dict = await resp.json(content_type=None)
        except aiohttp.ClientConnectorError:
            yield event.plain_result("❌ 无法连接到 SimPass 服务器，请检查网络或稍后重试。")
            return
        except aiohttp.ServerTimeoutError:
            yield event.plain_result("❌ 请求超时，SimPass 服务器未响应。")
            return
        except Exception as e:
            logger.error(f"[SimpassOTP] 请求异常：{e}")
            yield event.plain_result(f"❌ 请求出错：{e}")
            return

        # 构建返回消息
        code = data.get("code", -1)
        msg = data.get("msg", "未知信息")
        user_info: dict = data.get("user_info", {})

        if code == 200:
            simpass_uid = user_info.get("simpass_uid", "N/A")
            create_time = user_info.get("create_time", "N/A")
            level = user_info.get("level", "N/A")
            risky = user_info.get("risky", False)
            risky_text = "⚠️ 是（已被标记）" if risky else "✅ 否"

            result_text = (
                f"✅ 验证成功\n"
                f"━━━━━━━━━━━━━━\n"
                f"SimPass UID：{simpass_uid}\n"
                f"注册时间：{create_time}\n"
                f"验证等级：{level}\n"
                f"风险标记：{risky_text}\n"
                f"━━━━━━━━━━━━━━\n"
                f"消息：{msg}"
            )
        else:
            result_text = f"❌ 验证失败（code={code}）\n消息：{msg}"

        # 脱敏处理：替换响应中所有 UUID
        result_text = mask_uuid(result_text)

        yield event.plain_result(result_text)

    async def terminate(self):
        """插件卸载时调用。"""
        pass
