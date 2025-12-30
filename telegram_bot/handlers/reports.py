"""
Report handlers for the Telegram bot.
Contains commands for generating various reports and analytics.
"""

import asyncio

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from telegram_bot.utils import check_admin, add_admin_to_config
from telegram_bot.keyboards import create_back_to_main_keyboard
from utils.read_config import read_config
from utils.connection_analyzer import (
    generate_connection_report,
    generate_node_usage_report,
    get_multi_device_users,
    get_users_by_node,
    get_users_by_inbound_protocol
)


async def _send_response(update: Update, text: str, parse_mode: str = "HTML", reply_markup=None):
    """
    Helper to send response in both message and callback query contexts.
    """
    if update.callback_query:
        # In callback query context, answer the callback first
        await update.callback_query.answer()
        # Then send a new message (can't use edit for long reports)
        await update.callback_query.message.reply_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    elif update.message:
        await update.message.reply_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )


async def check_admin_privilege(update: Update):
    """
    Checks if the user has admin privileges.
    """
    admins = await check_admin()
    if not admins:
        await add_admin_to_config(update.effective_chat.id)
    admins = await check_admin()
    if update.effective_chat.id not in admins:
        await _send_response(
            update,
            "Sorry, you do not have permission to execute this command."
        )
        return ConversationHandler.END


async def connection_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send connection analysis report."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        report = await generate_connection_report()
        # Split long messages to avoid Telegram's message length limit
        max_length = 4000
        if len(report) <= max_length:
            await _send_response(update, f"<code>{report}</code>")
        else:
            # Split the report into smaller chunks
            chunks = [report[i:i+max_length] for i in range(0, len(report), max_length)]
            for i, chunk in enumerate(chunks):
                await _send_response(
                    update, 
                    f"<code>Part {i+1}/{len(chunks)}:\n{chunk}</code>"
                )
    except Exception as e:
        await _send_response(update, f"Error generating report: {str(e)}")


async def node_usage_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send node usage report."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        report = await generate_node_usage_report()
        await _send_response(update, f"<code>{report}</code>")
    except Exception as e:
        await _send_response(update, f"Error generating report: {str(e)}")


async def multi_device_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show users identified as using multiple devices."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        multi_device_users = await get_multi_device_users()
        if not multi_device_users:
            await _send_response(update, "No multi-device users detected.")
            return
        
        report_lines = ["<b>Multi-Device Users:</b>\n"]
        for username, ip_count, node_count, protocols in multi_device_users:
            report_lines.append(f"<code>{username}</code>")
            report_lines.append(f"  • {ip_count} unique IPs")
            report_lines.append(f"  • {node_count} different nodes")
            report_lines.append(f"  • Protocols: {', '.join(protocols)}")
            report_lines.append("")
        
        report = "\n".join(report_lines)
        await _send_response(update, report)
    except Exception as e:
        await _send_response(update, f"Error generating report: {str(e)}")


async def users_by_node_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show users by node. Usage: /users_by_node <node_id>"""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if not context.args:
        await _send_response(update, "Usage: /users_by_node <node_id>")
        return
    
    try:
        node_id = int(context.args[0])
        users_on_node = await get_users_by_node(node_id)
        
        if not users_on_node:
            await _send_response(update, f"No users found on node {node_id}.")
            return
        
        report_lines = [f"<b>Users on Node {node_id}:</b>\n"]
        for username, ip, protocol in users_on_node:
            report_lines.append(f"<code>{username}</code>")
            report_lines.append(f"  • IP: {ip}")
            report_lines.append(f"  • Protocol: {protocol}")
            report_lines.append("")
        
        report = "\n".join(report_lines)
        await _send_response(update, report)
    except ValueError:
        await _send_response(update, "Invalid node ID. Please provide a valid number.")
    except Exception as e:
        await _send_response(update, f"Error generating report: {str(e)}")


async def users_by_protocol_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show users by inbound protocol. Usage: /users_by_protocol <protocol>"""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if not context.args:
        await _send_response(
            update, 
            "Usage: /users_by_protocol <protocol>\nExample: /users_by_protocol \"Vless Direct\""
        )
        return
    
    try:
        protocol = " ".join(context.args)
        users_with_protocol = await get_users_by_inbound_protocol(protocol)
        
        if not users_with_protocol:
            await _send_response(update, f"No users found using protocol '{protocol}'.")
            return
        
        report_lines = [f"<b>Users using protocol '{protocol}':</b>\n"]
        for username, ip, node_name in users_with_protocol:
            report_lines.append(f"<code>{username}</code>")
            report_lines.append(f"  • IP: {ip}")
            report_lines.append(f"  • Node: {node_name}")
            report_lines.append("")
        
        report = "\n".join(report_lines)
        await _send_response(update, report)
    except Exception as e:
        await _send_response(update, f"Error generating report: {str(e)}")


async def ip_history_12h_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show users exceeding limits in last 12 hours"""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        await _send_response(update, "⏳ Generating 12-hour IP history report...")
        
        from utils.ip_history_tracker import ip_history_tracker
        from utils.isp_detector import ISPDetector
        
        config_data = await read_config()
        
        # Get ISP detector with token if available
        isp_detector = None
        ipinfo_token = config_data.get("IPINFO_TOKEN", "")
        use_fallback_api = config_data.get("USE_FALLBACK_ISP_API", False)
        if ipinfo_token or use_fallback_api:
            isp_detector = ISPDetector(token=ipinfo_token, use_fallback_only=use_fallback_api)
        
        # Generate report
        report = await ip_history_tracker.generate_report(12, config_data, isp_detector)
        
        # Split if too long (Telegram limit)
        if len(report) > 4000:
            # Split into chunks
            chunks = []
            lines = report.split("\n")
            current_chunk = []
            current_length = 0
            
            for line in lines:
                if current_length + len(line) + 1 > 3500:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_length = len(line)
                else:
                    current_chunk.append(line)
                    current_length += len(line) + 1
            
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            
            # Send chunks - get the message object for sending
            if update.callback_query:
                msg = update.callback_query.message
            else:
                msg = update.message
            
            for i, chunk in enumerate(chunks):
                if i > 0:
                    chunk = f"<b>Part {i+1}/{len(chunks)}</b>\n\n" + chunk
                await msg.reply_text(chunk, parse_mode="HTML")
                if i < len(chunks) - 1:
                    await asyncio.sleep(1)
        else:
            await _send_response(update, report)
            
    except Exception as e:
        await _send_response(update, f"Error generating report: {str(e)}")
        import traceback
        traceback.print_exc()


async def ip_history_48h_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show users exceeding limits in last 48 hours"""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        await _send_response(update, "⏳ Generating 48-hour IP history report...")
        
        from utils.ip_history_tracker import ip_history_tracker
        from utils.isp_detector import ISPDetector
        
        config_data = await read_config()
        
        # Get ISP detector with token if available
        isp_detector = None
        ipinfo_token = config_data.get("IPINFO_TOKEN", "")
        use_fallback_api = config_data.get("USE_FALLBACK_ISP_API", False)
        if ipinfo_token or use_fallback_api:
            isp_detector = ISPDetector(token=ipinfo_token, use_fallback_only=use_fallback_api)
        
        # Generate report
        report = await ip_history_tracker.generate_report(48, config_data, isp_detector)
        
        # Split if too long (Telegram limit)
        if len(report) > 4000:
            # Split into chunks
            chunks = []
            lines = report.split("\n")
            current_chunk = []
            current_length = 0
            
            for line in lines:
                if current_length + len(line) + 1 > 3500:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_length = len(line)
                else:
                    current_chunk.append(line)
                    current_length += len(line) + 1
            
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            
            # Send chunks - get the message object for sending
            if update.callback_query:
                msg = update.callback_query.message
            else:
                msg = update.message
            
            for i, chunk in enumerate(chunks):
                if i > 0:
                    chunk = f"<b>Part {i+1}/{len(chunks)}</b>\n\n" + chunk
                await msg.reply_text(chunk, parse_mode="HTML")
                if i < len(chunks) - 1:
                    await asyncio.sleep(1)
        else:
            await _send_response(update, report)
            
    except Exception as e:
        await _send_response(update, f"Error generating report: {str(e)}")
        import traceback
        traceback.print_exc()
