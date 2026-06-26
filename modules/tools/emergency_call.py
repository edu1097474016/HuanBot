"""紧急呼救功能模块"""
import os
import subprocess
import uuid
import time
import html
from typing import Optional
import requests
from core.config import config
from core.logger import logger


def get_emergency_phone_number(phone_number: Optional[str] = None) -> str:
    """获取紧急呼救电话号码"""
    phone = phone_number or config.get("emergency.phone_number")
    if not phone:
        raise ValueError("缺少紧急呼救号码，请在 config.json 的 emergency.phone_number 中配置。")
    return str(phone).strip()


def synthesize_tts(text: str, output_path: Optional[str] = None) -> str:
    """合成语音（使用本地TTS）"""
    if not output_path:
        output_dir = os.path.join(os.getcwd(), "data", "emergency")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"emergency_call_{int(time.time())}.wav")

    # 使用本地TTS (pyttsx3)
    try:
        import pyttsx3
        
        engine = pyttsx3.init()
        # 设置中文语音
        voices = engine.getProperty('voices')
        for v in voices:
            if 'zh' in v.languages or 'Chinese' in v.name:
                engine.setProperty('voice', v.id)
                break
        
        # 设置语速
        engine.setProperty('rate', 150)
        
        # 保存到文件
        engine.save_to_file(text, output_path)
        engine.runAndWait()
        engine.stop()
        
        logger.info("紧急呼救", f"已使用本地TTS生成语音文件: {output_path}")
        return output_path
    except ImportError:
        logger.error("紧急呼救", "pyttsx3库未安装，请安装: pip install pyttsx3")
        raise
    except Exception as e:
        logger.error("紧急呼救", f"本地TTS生成失败: {e}")
        raise


def check_adb_connectivity(adb_path: str) -> None:
    """检查ADB连接状态"""
    try:
        result = subprocess.run([adb_path, "devices"], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        if "device" not in result.stdout.replace("\r", "\n"):
            raise RuntimeError("未检测到连接的设备，请确认 adb 已连接手机。")
        logger.info("紧急呼救", f"ADB 设备连接正常: {adb_path}")
    except Exception as e:
        raise RuntimeError(f"ADB 检查失败: {e}")


def dial_phone_number(phone_number: str, adb_path: str) -> None:
    """拨打电话"""
    cmd = [adb_path, "shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{phone_number}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    logger.info("紧急呼救", f"已发起拨号请求: {phone_number}")


def push_audio_to_phone(local_path: str, adb_path: str) -> str:
    """推送音频文件到手机"""
    remote_path = "/sdcard/huanbot_emergency.wav"
    cmd = [adb_path, "push", local_path, remote_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    logger.info("紧急呼救", f"已推送语音文件到手机: {remote_path}")
    return remote_path


def play_audio_on_phone(remote_path: str, adb_path: str) -> None:
    """在手机上播放音频"""
    cmd = [adb_path, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"file://{remote_path}", "-t", "audio/wav"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    logger.info("紧急呼救", f"已尝试在手机上播放求救语音: {remote_path}")


def emergency_call(location: str, details: str, user_name: Optional[str] = None, 
                   phone_number: Optional[str] = None, extra_info: Optional[str] = None) -> dict:
    """
    发起紧急呼救
    
    Args:
        location: 求助者位置
        details: 求助者详细情况
        user_name: 求助者姓名（可选）
        phone_number: 紧急联系电话（可选，默认使用配置中的号码）
        extra_info: 额外信息（可选）
    
    Returns:
        呼救结果字典
    """
    phone_number = get_emergency_phone_number(phone_number)
    if not user_name:
        user_name = "未知求助者"
    if not location:
        raise ValueError("紧急呼救必须提供求助者位置。")
    if not details:
        raise ValueError("紧急呼救必须提供求助者详细情况。")

    message = (
        f"紧急求助：{user_name} 需要帮助。"
        f"位置：{location}。"
        f"情况说明：{details}。"
    )
    if extra_info:
        message += f" 额外信息：{extra_info}。"

    logger.info("紧急呼救", f"准备呼救，号码={phone_number}，求助者={user_name}，位置={location}")
    wav_path = synthesize_tts(message, None)
    
    # 在电脑上直接播放语音
    try:
        import winsound
        winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        logger.info("紧急呼救", f"已在电脑上播放求救语音")
    except Exception as e:
        logger.error("紧急呼救", f"电脑播放语音失败: {e}")
    
    # 拨打紧急电话（保留ADB功能但不依赖它）
    adb_path = config.get("emergency.adb_path") or "adb"
    try:
        check_adb_connectivity(adb_path)
        dial_phone_number(phone_number, adb_path)
        logger.info("紧急呼救", f"已通过ADB拨打紧急电话: {phone_number}")
    except Exception as e:
        logger.warning("紧急呼救", f"ADB拨打失败，但仍会继续播放语音: {e}")
    
    # 发送群公告通知群成员
    try:
        from core.api_manager import get_api_manager
        group_id = config.get("bot.group_id")
        if group_id:
            notice_content = f"🚨【紧急求助通知】\n\n" \
                           f"求助者：{user_name}\n" \
                           f"位置：{location}\n" \
                           f"情况：{details}\n"
            if extra_info:
                notice_content += f"额外信息：{extra_info}\n"
            notice_content += f"\n已拨打紧急电话：{phone_number}\n" \
                           f"请相关人员关注情况并提供帮助！"
            result = get_api_manager().send_group_notice(group_id, notice_content)
            logger.info("紧急呼救", f"已发送群公告通知")
    except Exception as e:
        logger.error("紧急呼救", f"发送群公告失败: {e}")
    
    return {
        "status": "ok",
        "phone_number": phone_number,
        "message": message,
        "audio_file": wav_path
    }
