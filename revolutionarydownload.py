from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, InlineQueryResultAudio, InlineQueryResultPhoto, InputTextMessageContent, InlineQueryResultArticle, URLInputFile
from aiogram.types.input_media_audio import InputMediaAudio
from spotipy import SpotifyClientCredentials, Spotify
from aiogram.filters import Command, CommandObject
from aiogram import Bot, Dispatcher, types
from yt_dlp import *
import requests
import hashlib
import asyncio
import logging
import json
import os

#see how to obtain spotify tokens: https://developer.spotify.com/documentation/web-api/concepts/apps

TELEGRAM_API_TOKEN = '123456789:qwertyuiopasdfghjklzxcvbb'
SPOTIPY_CLIENT_ID = '273a7dc9a509c8746fd0fb124eb9ef72'
SPOTIPY_CLIENT_SECRET = 'a25a8aac15f0a98a9555ef61dc833385'
CHANNEL_ID = -100123456789 #since telegram requires file_id in order to edit audio in message sent by inline query, you need other chat(channel) where bot can upload files and take their file_id
logging.basicConfig(level=logging.INFO)

def sanitize_song_name(name: str) -> str:
    if " - " in name:
        name = name.replace(" - ", " (") + ")"

    return name.lower()

class spotipy_wrap:
    def __init__(self, client_id, client_secret, download_dir="downloads"):
          self.spotify = Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id,client_secret=client_secret))
          self.download_dir = download_dir
          
    def __search_youtube(self, search_query:str, max_results=10):
        options = {
            'format': 'best',
            'extract_flat': True
        }

        with YoutubeDL(options) as ydl:
            search_results = ydl.extract_info(f'ytsearch{max_results}:{search_query}', download=False)
        
            videos = []
            for entry in search_results['entries']:
                video_info = {
                    'title': entry['title'],
                    'url': entry['url'],
                    'duration': entry['duration'],
                }
                videos.append(video_info)

            return videos  
        
    def __download_youtube_video(self, url:str, format:str, output_path="%(title)s.%(ext)s"):
        options = {
            'format': 'bestaudio/best',
            'extractaudio': True,
            'audioformat': format,
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format,
                'preferredquality': '360',
            }],
        }

        with YoutubeDL(options) as ydl:
            ydl.download([url])
            
    def __duration_near(self, dur1, dur2, tolerance=0.1):
        diff = abs(dur1 - dur2)
        return diff <= tolerance

    def download(self, spotify_url:str, format_str:str) -> bool:
        track = self.spotify.track(spotify_url)

        performer_str = ", ".join([artist['name'] for artist in track['artists']])
        
        name = track['name']
        
        query = f"{performer_str} {name}"
        
        if os.path.exists(os.path.join(self.download_dir, hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest() + f".{format_str}")):
            return True
        
        results = self.__search_youtube(search_query=query)

        for idx, video in enumerate(results, start=1):
            print(f"{video['title'].lower()} / {name} / {sanitize_song_name(name)}")
            if video['title'] == name:
                self.__download_youtube_video(video['url'], format_str, os.path.join(self.download_dir, hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest()))
                return True
            elif sanitize_song_name(name) in video['title'].lower() and self.__duration_near(float(video['duration']), (float(track['duration_ms']) / 1000), tolerance=1.5):
                self.__download_youtube_video(video['url'], format_str, os.path.join(self.download_dir, hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest()))
                return True
            
        return False

bot = Bot(token=TELEGRAM_API_TOKEN)
dp = Dispatcher()
s = spotipy_wrap(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET, download_dir="downloads")

async def upload_file_and_get_file_id(file_path:str,thumb_url:str,track_title:str,performer_str:str,duration:int) -> str:
    try:
        m = await bot.send_audio(CHANNEL_ID, FSInputFile(path=file_path), thumbnail=URLInputFile(url=thumb_url), title=track_title, performer=performer_str, duration=int(duration))
        return m.audio.file_id
    except Exception as e:
        return f"failed: {str(e)}"
    
async def format_artists(song_object):
    return ", ".join([artist['name'] for artist in song_object['artists']])

async def get_formatted_track_list(recommendations):
    return "\n".join([f"{track['artists'][0]['name']} - {track['name']}: {track['external_urls']['spotify']}" for track in recommendations['tracks']])

async def get_formatted_similar_artists(related_artists):
    return "\n".join([f"{artist['name']}, genres: {artist['genres']}: {artist['external_urls']['spotify']}" for artist in related_artists['artists']])

@dp.message(Command("start"))
async def start_cmd(message: types.Message, command:CommandObject) -> None:
    return

@dp.chosen_inline_result(lambda chosen_inline_result: True)
async def on_chosen_inline_result(chosen_inline_result: types.ChosenInlineResult):
    if not chosen_inline_result.inline_message_id:
        print('id is 0, aborting')
        return

    track = s.spotify.track(chosen_inline_result.query)

    format_str = ""
    if chosen_inline_result.result_id == "mp3_request":
        format_str = "mp3" 
    if chosen_inline_result.result_id == "flac_request":
        format_str = "flac" 
    if chosen_inline_result.result_id == "m4a_request":
        format_str = "m4a" 
        
    download_status = s.download(chosen_inline_result.query, format_str) #download track by given link into specified directory
    #this class (spotipy_wrap) uses spotify api to generate a search query for youtube, find a video on youtube and download it
    
    if not download_status:
        await bot.edit_message_text(
            inline_message_id=chosen_inline_result.inline_message_id, 
            text=f"⛔ unable to download {track['name']}")
        return

    performer_str = await format_artists(track)

    path = os.path.join("downloads", hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest() + f".{format_str}")

    file_id = await upload_file_and_get_file_id(
        file_path=path,
        thumb_url=track['album']['images'][1]['url'], #get 320x320 artwork since telegram api requires that resolution
        track_title=track['name'],
        performer_str=performer_str,
        duration=int(track['duration_ms']) / 1000)
    
    if file_id.startswith("failed"):
        await bot.edit_message_text(
            inline_message_id=chosen_inline_result.inline_message_id, 
            text=file_id.replace(TELEGRAM_API_TOKEN, ''))
        return

    await bot.edit_message_media(
        inline_message_id=chosen_inline_result.inline_message_id, 
        media=InputMediaAudio(media=file_id))

    await asyncio.sleep(86400) #wait for 24h and delete downloaded file
    if os.path.exists(path): os.remove(path)

async def get_big_artwork(isrc: str) -> str:
    response = requests.get(f"https://api.deezer.com/track/isrc:{isrc}")
    deezer_json_response = json.loads(response.text)
    return deezer_json_response['album']['cover_xl']

async def get_big_artwork_fullsize(isrc: str) -> str:
    response = requests.get(f"https://api.deezer.com/track/isrc:{isrc}")
    deezer_json_response = json.loads(response.text)
    return deezer_json_response['album']['cover_xl'][:-27] + "1900x1900.png"

@dp.inline_query(lambda query: True)
async def on_inline_query(query: InlineQuery):
    try: #ensure given query is valid spotify track (single)
        track = s.spotify.track(query.query)
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
    analysis = s.spotify.audio_analysis(query.query)
    recommendations = s.spotify.recommendations(seed_tracks=[query.query], limit=5)
    related_artists = s.spotify.artist_related_artists(track['artists'][0]['external_urls']['spotify'])
    resolved_artist = s.spotify.artist(track['artists'][0]['external_urls']['spotify'])
    genres_of_resolved_artist = resolved_artist['genres']

    if genres_of_resolved_artist == []:
        genres_of_resolved_artist += ['failed_to_detect']

    if not preview_url: #if spotify api didn't gave us 30-second preview, display only artwork and return
        results = [
            InlineQueryResultPhoto(
                id='photo_request',
                title=f"{track['artists'][0]['name']} - {track['name']}",
                thumbnail_url=f"{track['album']['images'][0]['url']}",
                photo_url=await get_big_artwork(track['external_ids']['isrc']),
                description=f"artwork of {track['name']}"
            ),
            InlineQueryResultArticle(
                id='dict_request',
                title=f"JSON object of {track['name']}",
                input_message_content=InputTextMessageContent(message_text=f"{track}"),
                thumbnail_url="https://i.imgur.com/zpPuV4Y.jpeg"
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
            photo_url=await get_big_artwork(track['external_ids']['isrc']),
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
        
async def download_album(user_id: int, album_object) -> None:
    await bot.send_photo(user_id, 
                             await get_big_artwork(s.spotify.track(album_object['tracks']['items'][0]['external_urls']['spotify'])['external_ids']['isrc']),
                             caption=f"[{album_object['artists'][0]['name']} - {album_object['name']}]({album_object['external_urls']['spotify']})\n[1900x1900 .png artwork]({await get_big_artwork_fullsize(s.spotify.track(album_object['tracks']['items'][0]['external_urls']['spotify'])['external_ids']['isrc'])}", 
                             parse_mode="markdown")

    for track in album_object['tracks']['items']:
        download_status = s.download(track['external_urls']['spotify'], "mp3")
        if download_status is False:
            await bot.send_message(user_id, f"⛔ unable to download {track['name']}")
            continue

        await bot.send_audio(user_id,
                                audio=FSInputFile(path=os.path.join("downloads", hashlib.md5(f"{await format_artists(track)} - {track['name']}".encode('utf-8')).hexdigest() + ".mp3")),
                                thumbnail=URLInputFile(url=album_object['images'][1]['url']),
                                title=track['name'],
                                performer=await format_artists(track),
                                duration=int(int(track['duration_ms']) / 1000))
            
        os.remove(os.path.join("downloads", hashlib.md5(f"{await format_artists(track)} - {track['name']}".encode('utf-8')).hexdigest() + ".mp3"))
        
    return

async def download_single(user_id: int, track_object) -> None:
    download_status = s.download(track_object['external_urls']['spotify'], "mp3")
    if download_status is False:
        return
    
    await bot.send_photo(user_id, await get_big_artwork(track_object['external_ids']['isrc']), caption=f"[{await format_artists(track_object)} - {track_object['name']}]({track_object['external_urls']['spotify']})\n[1900x1900 .png artwork]({await get_big_artwork_fullsize(track_object['external_ids']['isrc'])})", parse_mode="markdown")
    await bot.send_audio(user_id,
                         audio=FSInputFile(path=os.path.join("downloads", hashlib.md5(f"{await format_artists(track_object)} - {track_object['name']}".encode('utf-8')).hexdigest() + ".mp3")),
                         thumbnail=URLInputFile(url=track_object['album']['images'][1]['url']),
                         title=track_object['name'],
                         performer=await format_artists(track_object),
                         duration=int(int(track_object['duration_ms']) / 1000))

    return True

@dp.callback_query()
async def callback_query_handler(callback_query: types.CallbackQuery):
    if callback_query.data.startswith("album:"): 
        alb = s.spotify.album(callback_query.data[6:])
        await callback_query.answer() 
        await download_album(callback_query, alb)

    track = s.spotify.track(callback_query.data)
    
    if not await download_single(callback_query.from_user.id, track):
        await callback_query.answer(f"⛔ unable to download {track['name']}", True)

    await callback_query.answer()

    return

@dp.message()
async def any_message(message: types.Message) -> None:
    if message.text.startswith("https://"):
        try:
            track = s.spotify.track(message.text)
        except Exception as e:
            if "Unexpected Spotify URL type" in f"{e}": #its an album
                await download_album(message.from_user.id, s.spotify.album(message.text))
                return
            
            await message.reply(f"⛔ invalid link")
            return
    
        if not await download_single(message.from_user.id, track):
            await message.reply(f"⛔ unable to download {track['name']}")
        return

    inline_keyboard = []
        
    search_response = s.spotify.search(f"{message.text}")
    search_response_album = s.spotify.search(f"{message.text}", type="album")

    for track, album_track in zip(search_response['tracks']['items'], search_response_album['albums']['items']):
        inline_keyboard.append([types.InlineKeyboardButton(text=f"{await format_artists(track)} - {track['name']}", callback_data=f"{track['external_urls']['spotify']}"),
                                types.InlineKeyboardButton(text=f"{album_track['artists'][0]['name']} - {album_track['name']}", callback_data=f"album:{album_track['external_urls']['spotify']}")])

    await message.reply(f"found: ", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=inline_keyboard))

async def main():
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())
