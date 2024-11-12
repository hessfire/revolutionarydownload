from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, InlineQueryResultAudio, InlineQueryResultPhoto, InputTextMessageContent, InlineQueryResultArticle, URLInputFile
import requests, hashlib, asyncio, logging, json, os, random, sqlite3
from aiogram.types.input_media_audio import InputMediaAudio
from spotipy import SpotifyClientCredentials, Spotify
from aiogram.filters import Command, CommandObject
from aiogram import Bot, Dispatcher, types
from ytmusicapi import YTMusic
from bs4 import BeautifulSoup
from sys import platform
from yt_dlp import *

#see how to obtain spotify tokens: https://developer.spotify.com/documentation/web-api/concepts/apps

TELEGRAM_API_TOKEN = '123456789:qwertyuiopasdfghjklzxcvbb'
SPOTIPY_CLIENT_ID = '273a7dc9a509c8746fd0fb124eb9ef72'
SPOTIPY_CLIENT_SECRET = 'a25a8aac15f0a98a9555ef61dc833385'
CHANNEL_ID = -100123456789 #since telegram requires file_id in order to edit audio in message sent by inline query, you need other chat(channel) where bot can upload files and take their file_id
logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_API_TOKEN)
dp = Dispatcher()
ytmusic = YTMusic()

class spotipy_wrap:
    def __init__(self, client_id, client_secret, download_dir="downloads"):
          self.spotify = Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id,client_secret=client_secret))
          self.download_dir = download_dir
          
    def __search_youtube(self, search_query:str, max_results=13):
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
            "cookiefile": "ck.txt",
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
            if video['title'] == name:
                self.__download_youtube_video(video['url'], format_str, os.path.join(self.download_dir, hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest()))
                return True
            elif sanitize_song_name(name) in video['title'].lower() and self.__duration_near(float(video['duration']), (float(track['duration_ms']) / 1000), tolerance=1.5):
                self.__download_youtube_video(video['url'], format_str, os.path.join(self.download_dir, hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest()))
                return True

        results = ytm_search(query)
        
        for video in results:
            if video['title'] == name:
                self.__download_youtube_video(video['url'], format_str, os.path.join(self.download_dir, hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest()))
                return True
            elif sanitize_song_name(name) in video['title'].lower() and self.__duration_near(float(video['duration']), (float(track['duration_ms']) / 1000), tolerance=1.5):
                self.__download_youtube_video(video['url'], format_str, os.path.join(self.download_dir, hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest()))
                return True
       
        return False

s = spotipy_wrap(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET, download_dir="downloads")

class cache:
    def __init__(self):
        self.conn = sqlite3.connect('cache.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS cache (hash TEXT, file_id TEXT)''')
        self.conn.commit()

    def add_file_id(self, hash, file_id):
        self.cursor.execute('INSERT INTO cache (hash, file_id) VALUES (?, ?)', (hash, file_id))
        self.conn.commit()

    def get_file_id(self, hash):
        self.cursor.execute(f'SELECT file_id FROM cache WHERE hash = ?', (hash,))
        result = self.cursor.fetchone()
        return result[0] if result else None

cache_manager = cache()

def ytm_search(query: str):
    search_results = ytmusic.search(query)
    out = []
    for result in search_results:
        if result['resultType'] != "song": continue
        out.append({"title": result['title'], "url": f"https://www.youtube.com/watch?v={result['videoId']}"})

    return out

def sanitize_song_name(name: str) -> str:
    if " - " in name:
        name = name.replace(" - ", " (") + ")"

    return name.lower()

async def upload_file_and_get_file_id(file_path: str, thumb_url: str, track_title: str, performer_str: str, duration: int) -> str:
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
        return

    format_str = "mp3"
    link = chosen_inline_result.query

    if "querymp3" in chosen_inline_result.result_id:
        link = chosen_inline_result.result_id.split("_")[1]

    track = s.spotify.track(link)

    if "_request" in chosen_inline_result.result_id: format_str = chosen_inline_result.result_id.replace("_request", "")
        
    performer_str = await format_artists(track)
    hash = hashlib.md5(f"{performer_str} - {track['name']}".encode('utf-8')).hexdigest()
    path = os.path.join("downloads", f"{hash}.{format_str}")
    database_file_id = cache_manager.get_file_id(hash)
    file_id = None

    if database_file_id:
        file_id = database_file_id
    else:
        download_status = s.download(link, format_str) #download track by given link into specified directory
        #this class (spotipy_wrap) uses spotify api to generate a search query for youtube, find a video on youtube and download it
    
        if not download_status:
            await bot.edit_message_text(
                inline_message_id=chosen_inline_result.inline_message_id, 
                text=f"⛔ unable to download {track['name']}")
            return

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

        cache_manager.add_file_id(hash, file_id)

    await bot.edit_message_media(
        inline_message_id=chosen_inline_result.inline_message_id, 
        media=InputMediaAudio(media=file_id))

    if os.path.exists(path): os.remove(path)

async def get_big_artwork(isrc: str) -> str:
    response = requests.get(f"https://api.deezer.com/track/isrc:{isrc}")
    deezer_json_response = json.loads(response.text)

    if "error" in deezer_json_response: return "https://failed.gg"

    return deezer_json_response['album']['cover_xl']

async def get_big_artwork_fullsize(isrc: str) -> str:
    response = requests.get(f"https://api.deezer.com/track/isrc:{isrc}")
    deezer_json_response = json.loads(response.text)
    
    if "error" in deezer_json_response: return "https://failed.gg"

    return deezer_json_response['album']['cover_xl'][:-27] + "1900x1900.png"

async def get_artwork_apple_music(query: str) -> str:
    response = requests.get(f"https://music.apple.com/us/search?term={query}")
    soup = BeautifulSoup(response.text, 'html.parser')
    hrefs = [a['href'] for a in soup.find_all('a', href=True) if "https://music.apple.com/us/album/" in a['href']]
    release_link = hrefs[0]
    response = requests.get(release_link)
    soup = BeautifulSoup(response.text, 'html.parser')
    srcsets = [picture['srcset'] for picture in soup.find_all('source', srcset=True) if "296x296bb.webp" in picture['srcset']]
    artwork_link = srcsets[0].split(" ")[0][:-14] + "99999x99999.png"
    return artwork_link

@dp.inline_query(lambda query: True)
async def on_inline_query(query: InlineQuery):
    try: #ensure given query is valid spotify track (single)
        track = s.spotify.track(query.query)
    except: #invalid link, or song name
        try: #trying to search songs with passed name
            if query.query == "": raise Exception()
            
            results = []
            
            search_response = s.spotify.search(query.query, limit=10)

            for track in search_response['tracks']['items']:
                if not track['preview_url']: continue
                
                results.append(InlineQueryResultArticle(
                    id='querymp3_' + track['external_urls']["spotify"],
                    title=f"{track['artists'][0]['name']} - {track['name']}",
                    input_message_content=InputTextMessageContent(message_text=f"downloading {track['artists'][0]['name']} - {track['name']}, usually it takes 5-10 seconds"),
                    thumbnail_url=track['album']['images'][0]['url'],
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="made with love by @beevil1337", url="https://t.me/beevil1337")]])
                ))

                results.append(InlineQueryResultPhoto(
                    id='photorequest_' + str(random.randint(3, 100)),
                    thumbnail_url=f"{track['album']['images'][0]['url']}",
                    photo_url=f"{track['album']['images'][0]['url']}",
                ))
       
            await bot.answer_inline_query(query.id, results=results)
            return
        
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
                photo_url=f"{track['album']['images'][0]['url']}",
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
        InlineQueryResultArticle(
            id='mp3_request',
            title=f"(mp3) {track['artists'][0]['name']} - {track['name']}",
            input_message_content=InputTextMessageContent(message_text=f"downloading {track['artists'][0]['name']} - {track['name']}, usually it takes 5-10 seconds"),
            thumbnail_url=track['album']['images'][0]['url'],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="made with love by @beevil1337", url="https://t.me/beevil1337")]])
        ),
        InlineQueryResultArticle(
            id='flac_request',
            title=f"(flac) {track['artists'][0]['name']} - {track['name']}",
            input_message_content=InputTextMessageContent(message_text=f"downloading {track['artists'][0]['name']} - {track['name']}, usually it takes 5-10 seconds"),
            thumbnail_url=track['album']['images'][0]['url'],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="made with love by @beevil1337", url="https://t.me/beevil1337")]])
        ),
        InlineQueryResultArticle(
            id='m4a_request',
            title=f"(m4a) {track['artists'][0]['name']} - {track['name']}",
            input_message_content=InputTextMessageContent(message_text=f"downloading {track['artists'][0]['name']} - {track['name']}, usually it takes 5-10 seconds"),
            thumbnail_url=track['album']['images'][0]['url'],
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
        # InlineQueryResultArticle(
        #     id='analysis_request',
        #     title=f"tempo of {track['name']} detected by spotify analysis",
        #     input_message_content=InputTextMessageContent(message_text=f"tempo of {track['name']} is {analysis['track']['tempo']}"),
        #     thumbnail_url="https://i.imgur.com/e3grrAM.jpeg"
        # ),
        # InlineQueryResultArticle(
        #     id='recommendations_request',
        #     title=f"recommendations based on {track['name']} generated by spotify api",
        #     input_message_content=InputTextMessageContent(message_text=f"recommended tracks based on {track['name']}:\n{await get_formatted_track_list(recommendations)}"),
        #     thumbnail_url="https://i.imgur.com/lTheQra.jpg"
        # ),
        # InlineQueryResultArticle(
        #     id='related_artists_request',
        #     title=f"related(similar) artists to {track['artists'][0]['name']} generated by spotify api",
        #     input_message_content=InputTextMessageContent(message_text=f"similar artists to {track['artists'][0]['name']}:\n{await get_formatted_similar_artists(related_artists)}"),
        #     thumbnail_url="https://i.imgur.com/lTheQra.jpg"
        # ), 
        # InlineQueryResultArticle(
        #     id='genres_request',
        #     title=f"genres of {track['artists'][0]['name']} detected by spotify api",
        #     input_message_content=InputTextMessageContent(message_text=f"detected genres of {track['artists'][0]['name']} are {str(genres_of_resolved_artist)}"),
        #     thumbnail_url="https://i.imgur.com/wyZwZN7.jpg"
        # )
    ]    

    await bot.answer_inline_query(query.id, results=results)
        
async def download_album(user_id: int, album_object) -> None:
    artwork_url = await get_big_artwork(s.spotify.track(album_object['tracks']['items'][0]['external_urls']['spotify'])['external_ids']['isrc'])
    if artwork_url == 'https://failed.gg': artwork_url = album_object['album']['images'][0]['url']

    await bot.send_photo(user_id, 
                             artwork_url,
                             caption=f"[{album_object['artists'][0]['name']} - {album_object['name']}]({album_object['external_urls']['spotify']})\n[1900x1900 .png artwork]({await get_big_artwork_fullsize(s.spotify.track(album_object['tracks']['items'][0]['external_urls']['spotify'])['external_ids']['isrc'])}", 
                             parse_mode="markdown")

    for track in album_object['tracks']['items']:
        hash = hashlib.md5(f"{await format_artists(track)} - {track['name']}".encode('utf-8')).hexdigest()
        path = os.path.join("downloads", f"{hash}.mp3")
        database_file_id = cache_manager.get_file_id(hash)
        
        if database_file_id:
            await bot.send_audio(user_id, audio=database_file_id)
        else:
            download_status = s.download(track['external_urls']['spotify'], "mp3")
            if download_status is False:
                await bot.send_message(user_id, f"⛔ unable to download {track['name']}")
                continue

            response = await bot.send_audio(user_id,
                                    audio=FSInputFile(path=path),
                                    thumbnail=URLInputFile(url=album_object['images'][1]['url']),
                                    title=track['name'],
                                    performer=await format_artists(track),
                                    duration=int(int(track['duration_ms']) / 1000))

            cache_manager.add_file_id(hash, response.audio.file_id)
            
        if os.path.exists(path): os.remove(path)
        
    return

async def download_single(user_id: int, track_object) -> None:
    artwork_url = await get_big_artwork(track_object['external_ids']['isrc'])
    if artwork_url == 'https://failed.gg': artwork_url = track_object['album']['images'][0]['url']
    hash = hashlib.md5(f"{await format_artists(track_object)} - {track_object['name']}".encode('utf-8')).hexdigest()
    path = os.path.join("downloads", f"{hash}.mp3")
    await bot.send_photo(user_id, artwork_url, caption=f"[{await format_artists(track_object)} - {track_object['name']}]({track_object['external_urls']['spotify']})\n[1900x1900 .png artwork]({await get_big_artwork_fullsize(track_object['external_ids']['isrc'])})\n[original resolution .png artwork]({await get_artwork_apple_music(track_object['artists'][0]['name'] + ' ' + track_object['name'])})", parse_mode="markdown")    

    database_file_id = cache_manager.get_file_id(hash)
        
    if database_file_id:
        await bot.send_audio(user_id, audio=database_file_id)
    else:
        download_status = s.download(track_object['external_urls']['spotify'], "mp3")
        if download_status is False:
            return
    
        response = await bot.send_audio(user_id,
                             audio=FSInputFile(path=path),
                             thumbnail=URLInputFile(url=track_object['album']['images'][1]['url']),
                             title=track_object['name'],
                             performer=await format_artists(track_object),
                             duration=int(int(track_object['duration_ms']) / 1000))

        cache_manager.add_file_id(hash, response.audio.file_id)
        
    if os.path.exists(path): os.remove(path)
    return True

@dp.callback_query()
async def callback_query_handler(callback_query: types.CallbackQuery):
    if callback_query.data.startswith("album:"): 
        alb = s.spotify.album(callback_query.data[6:])
        await callback_query.answer() 
        await download_album(callback_query.from_user.id, alb)

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

    await message.reply(f"found (left side - singles, right side - albums): ", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=inline_keyboard))

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    if platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
