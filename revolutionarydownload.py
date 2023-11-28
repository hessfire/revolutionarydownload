from aiogram.types.inline_query_result import InlineQueryResult
from aiogram.types.input_file import InputFile
from aiogram.types.input_media_audio import InputMediaAudio
from savify import Savify
from savify.types import Type, Format, Quality
from savify.utils import PathHolder
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, InlineQueryResultAudio, InlineQueryResultCachedAudio, InlineQueryResultCachedPhoto, InlineQueryResultPhoto, InputTextMessageContent, InlineQueryResultArticle, URLInputFile, inline_query_result_audio
from savify.logger import Logger
import asyncio
import logging
import os
import sys

#see how to obtain spotify tokens: https://developer.spotify.com/documentation/web-api/concepts/apps

TELEGRAM_API_TOKEN = '123456789:qwertyuiopasdfghjklzxcvbb'
SPOTIPY_CLIENT_ID = '273a7dc9a509c8746fd0fb124eb9ef72'
SPOTIPY_CLIENT_SECRET = 'a25a8aac15f0a98a9555ef61dc833385'
CHANNEL_ID = -100123456789 #since telegram requires file_id in order to edit audio in message sent by inline query, you need other chat(channel) where bot can upload files and take their file_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spotipylog")
logger.addHandler(logging.StreamHandler(sys.stdout))

bot = Bot(token=TELEGRAM_API_TOKEN)
dp = Dispatcher()
s = Savify(api_credentials=(SPOTIPY_CLIENT_ID,SPOTIPY_CLIENT_SECRET), logger=logger, quality=Quality.BEST, download_format=Format.MP3, path_holder=PathHolder(downloads_path="downloads"))

async def upload_file_and_get_file_id(file_path:str,thumb_url:str,track_title:str,performer_str:str,duration:int) -> str:
    try:
        m = await bot.send_audio(CHANNEL_ID, FSInputFile(path=file_path), thumbnail=URLInputFile(url=thumb_url), title=track_title, performer=performer_str, duration=int(duration))
        return m.audio.file_id
    except Exception as e:
        return f"failed: {str(e)}"

async def get_formatted_track_list(recommendations):
    result = ""
    for track in recommendations['tracks']:
        result += f"{track['artists'][0]['name']} - {track['name']}: {track['external_urls']['spotify']}\n"
    return result

async def get_formatted_similar_artists(related_artists):
    result = ""
    for artist in related_artists['artists']:
        result += f"{artist['name']}, genres: {artist['genres']}: {artist['external_urls']['spotify']}\n"
    return result

@dp.chosen_inline_result(lambda chosen_inline_result: True)
async def on_chosen_inline_result(chosen_inline_result: types.ChosenInlineResult):
    if not chosen_inline_result.inline_message_id:
        print('id is 0, aborting')
        return

    track = s.spotify.sp.track(chosen_inline_result.query)

    format_str = ""
    if chosen_inline_result.result_id == "mp3_request":
        format_str = "mp3" 
        s.download_format = Format.MP3
    if chosen_inline_result.result_id == "flac_request":
        format_str = "flac" 
        s.download_format = Format.FLAC
    if chosen_inline_result.result_id == "m4a_request":
        format_str = "m4a" 
        s.download_format = Format.M4A
        
    s.download(chosen_inline_result.query) #download track by given link into specified directory
    #this library (savify) uses spotify api to generate a search query for youtube, find a video on youtube and download it
    #probably there is better libraries to download tracks by spotify link, but i use this for now
    
    performer_str=track['artists'][0]['name']

    if len(track['artists']) > 0: #generate string in format "artist1, artist2, artist3" if there is more than 1 artist present
        for x in track['artists']:
            if x['name'] not in performer_str: performer_str += f", {x['name']}"

    file_id = await upload_file_and_get_file_id(
        file_path=os.path.join("downloads", f"{track['artists'][0]['name']} - {track['name']}.{format_str}"),
        thumb_url=track['album']['images'][1]['url'], #get 320x320 artwork since telegram api requires that resolution
        track_title=track['name'],
        performer_str=performer_str,
        duration=int(track['duration_ms']) / 1000)
    
    if file_id.startswith("failed"):
        await bot.edit_message_text(
            inline_message_id=chosen_inline_result.inline_message_id, 
            text=file_id.replace(TELEGRAM_API_TOKEM, ''))
        return

    await bot.edit_message_media(
        inline_message_id=chosen_inline_result.inline_message_id, 
        media=InputMediaAudio(media=file_id))

    path = os.path.join("downloads", f"{track['artists'][0]['name']} - {track['name']}.{format_str}")

    await asyncio.sleep(86400) #wait for 24h and delete downloaded file
    if os.path.exists(path): os.remove(path)

@dp.inline_query(lambda query: True)
async def on_inline_query(query: InlineQuery):
    try: #ensure given query is valid spotify track (single)
        track = s.spotify.sp.track(query.query)
    except:
        results = [
            InlineQueryResultArticle(
                id='2',
                title=f"enter a valid spotify link",
                input_message_content=InputTextMessageContent(message_text='no valid link was provided')
            )
        ]
        await bot.answer_inline_query(query.id, results=results)
        return

    preview_url = track['preview_url']
    analysis = s.spotify.sp.audio_analysis(query.query)
    recommendations = s.spotify.sp.recommendations(seed_tracks=[query.query], limit=5)
    related_artists = s.spotify.sp.artist_related_artists(track['artists'][0]['external_urls']['spotify'])
    resolved_artist = s.spotify.sp.artist(track['artists'][0]['external_urls']['spotify'])
    genres_of_resolved_artist = resolved_artist['genres']

    if genres_of_resolved_artist == []:
        genres_of_resolved_artist += ['failed_to_detect']

    if not preview_url: #if spotify api didn't gave us 30-second preview, display only artwork and return
        results = [
            InlineQueryResultPhoto(
                id='photo_request',
                title=f"{track['artists'][0]['name']} - {track['name']}",
                thumbnail_url=f"{track['album']['images'][0]['url']}",
                photo_url=f"{track['album']['images'][0]['url']}",
                description=f"artwork of {track['name']}"
            )
        ]
        await bot.answer_inline_query(query.id, results=results)
        return
    
    track['available_markets'] = None #fixes "message too long" issue

    results = [
        InlineQueryResultAudio(
            id='mp3_request',
            audio_url=preview_url,
            title=f"(mp3) {track['artists'][0]['name']} - {track['name']}",
            caption="wait until track download is finished, usually it takes 5-10 seconds",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="made with love by @beevil1337", url="https://t.me/beevil1337")]])
        ),
        InlineQueryResultAudio(
            id='flac_request',
            audio_url=preview_url,
            title=f"(flac) {track['artists'][0]['name']} - {track['name']}",
            caption="wait until track download is finished, usually it takes 5-10 seconds",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="made with love by @beevil1337", url="https://t.me/beevil1337")]])
        ),
        InlineQueryResultAudio(
            id='m4a_request',
            audio_url=preview_url,
            title=f"(m4a) {track['artists'][0]['name']} - {track['name']}",
            caption="wait until track download is finished, usually it takes 5-10 seconds",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="made with love by @beevil1337", url="https://t.me/beevil1337")]])
        ),
        InlineQueryResultPhoto(
            id='photo_request',
            title=f"{track['artists'][0]['name']} - {track['name']}",
            thumbnail_url=f"{track['album']['images'][0]['url']}",
            photo_url=f"{track['album']['images'][0]['url']}",
            description=f"artwork of {track['name']}"
        ),
        InlineQueryResultArticle(
            id='dict_request',
            title=f"JSON object of {track['name']}",
            input_message_content=InputTextMessageContent(message_text=f"{track}"),
            thumbnail_url="https://i.imgur.com/zpPuV4Y.jpeg"
        ),
        InlineQueryResultArticle(
            id='analysis_request',
            title=f"tempo of {track['name']} detected by spotify analysis",
            input_message_content=InputTextMessageContent(message_text=f"tempo of {track['name']} is {analysis['track']['tempo']}"),
            thumbnail_url="https://i.imgur.com/e3grrAM.jpeg"
        ),
        InlineQueryResultArticle(
            id='recommendations_request',
            title=f"recommendations based on {track['name']} generated by spotify api",
            input_message_content=InputTextMessageContent(message_text=f"recommended tracks based on {track['name']}:\n{await get_formatted_track_list(recommendations)}"),
            thumbnail_url="https://i.imgur.com/lTheQra.jpg"
        ),
        InlineQueryResultArticle(
            id='related_artists_request',
            title=f"related(similar) artists to {track['artists'][0]['name']} generated by spotify api",
            input_message_content=InputTextMessageContent(message_text=f"similar artists to {track['artists'][0]['name']}:\n{await get_formatted_similar_artists(related_artists)}"),
            thumbnail_url="https://i.imgur.com/lTheQra.jpg"
        ), 
        InlineQueryResultArticle(
            id='genres_request',
            title=f"genres of {track['artists'][0]['name']} detected by spotify api",
            input_message_content=InputTextMessageContent(message_text=f"detected genres of {track['artists'][0]['name']} are {str(genres_of_resolved_artist)}"),
            thumbnail_url="https://i.imgur.com/wyZwZN7.jpg"
        )
    ]    

    await bot.answer_inline_query(query.id, results=results)

async def main():
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())
