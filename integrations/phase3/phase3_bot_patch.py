# JACC Phase 3 patch for bot.py
# Add this helper to the current Railway bot, then call it near the top of button_callback().

async def handle_web_payment_callback(query, context, data: str) -> bool:
    if not (data.startswith('webpay_approve_') or data.startswith('webpay_reject_')):
        return False
    if query.from_user.id not in ADMIN_IDS:
        await query.answer('Admin only', show_alert=True)
        return True

    approve = data.startswith('webpay_approve_')
    payment_id = data.replace('webpay_approve_', '').replace('webpay_reject_', '')
    action = 'approveWebPayment' if approve else 'rejectWebPayment'
    payload = {'action': action, 'paymentId': payment_id, 'adminId': str(query.from_user.id)}
    if not approve:
        payload['reason'] = 'Payment slip could not be verified'

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(SHEET_WEBHOOK, json=payload, timeout=20)
        result = response.json()
    except Exception as exc:
        logger.exception('website payment callback failed: %s', exc)
        await query.answer('Apps Script error', show_alert=True)
        return True

    if not result.get('ok'):
        await query.answer('Failed: ' + str(result.get('error', 'UNKNOWN')), show_alert=True)
        return True

    status = result.get('status', 'APPROVED' if approve else 'REJECTED')
    await query.answer(status)
    await query.edit_message_text(query.message.text + f'\n\n✅ Admin result: {status}')
    return True

# Add near the top of button_callback(), after query/data are defined:
# if await handle_web_payment_callback(query, context, data):
#     return
