async def _send_all(message: Message) -> None:
    games = await get_all_games(only_active=True)

    if not games:
        await message.answer("😔 Hozircha hech qanday o'yin mavjud emas.")
        return

    await message.answer(
        f"🎮 <b>Barcha o'yinlar ({len(games)} ta):</b>",
        parse_mode="HTML"
    )

    for game in games:
        try:
            await send_game_card(message, game)
        except Exception as e:
            await message.answer(
                f"❌ {game['slug']} xatosi:\n<code>{e}</code>",
                parse_mode="HTML"
            )
        await asyncio.sleep(0.3)