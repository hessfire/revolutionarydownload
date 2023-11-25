# ![logo2](https://github.com/hessfire/revolutionarydownload/assets/134144364/8a29d7a0-6945-4958-bcbf-9c7de10f5d32) revolutionarydownload
>simple telegram inline bot to download songs using a spotify link

***
## requirements
* `aiogram` | `pip install aiogram`
* `savify` | `pip install --use-pep517 git+https://github.com/stschake/savify@feature/use-yt-dlp`

***
## prerequisites
1. obtain your spotify api credentials at https://developer.spotify.com/documentation/web-api/concepts/apps
2. create a telegram bot using [@BotFather](t.me/BotFather) and get its token
3. create a new channel in telegram and add your bot as administrator into it
4. obtain id of your new channel (forward any message from your channel to  [@getmyid_bot](t.me/getmyid_bot) or enable "Show Peer IDs in Profile" in telegram desktop experimental settings and open channel info)
5. configure the script!

```py
TELEGRAM_API_TOKEN = '123456789:qwertyuiopasdfghjklzxcvbb'
SPOTIPY_CLIENT_ID = '273a7dc9a509c8746fd0fb124eb9ef72'
SPOTIPY_CLIENT_SECRET = 'a25a8aac15f0a98a9555ef61dc833385'
CHANNEL_ID = -100123456789 #since telegram requires file_id in order to edit audio in message sent by inline query, you need other chat(channel) where bot can upload files and take their file_id
```
***
