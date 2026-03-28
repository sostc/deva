#!/usr/bin/env python3
import json
import os
import subprocess
import random
import sys

PLAYLIST_FILE = "/Users/spark/pycharmproject/deva/playlist_cantonese.json"
MUSIC_DIR = "/tmp/cantonese_music"

class CantonesePlayer:
    def __init__(self):
        os.makedirs(MUSIC_DIR, exist_ok=True)
        self.load_playlist()
        self.current_index = 0
        self.repeat_single = False
        self.repeat_all = False
        self.shuffle = False
        self.original_order = []

    def load_playlist(self):
        with open(PLAYLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.songs = data['songs']
            self.name = data['name']
            self.description = data.get('description', '')

    def save_playlist(self):
        with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump({'name': self.name, 'description': self.description, 'songs': self.songs}, f, ensure_ascii=False, indent=2)

    def get_current_song(self):
        return self.songs[self.current_index]

    def show_playlist(self):
        print("\n" + "="*60)
        print(f"  {self.name}")
        print(f"  {self.description}")
        print("="*60)
        for i, song in enumerate(self.songs):
            marker = "▶ " if i == self.current_index else "  "
            print(f"{marker}{i+1:2d}. {song['title']} - {song['artist']} [{song['year']}] [{song['style']}]")
        print("="*60)
        print(f"共 {len(self.songs)} 首歌曲 | 当前: {self.current_index + 1}/{len(self.songs)}")
        print("="*60 + "\n")

    def add_song(self, title, artist, year, style='流行'):
        self.songs.append({'title': title, 'artist': artist, 'year': year, 'style': style})
        self.save_playlist()
        print(f"✓ 已添加: {title} - {artist}")

    def delete_song(self, index):
        if 0 <= index < len(self.songs):
            deleted = self.songs.pop(index)
            self.save_playlist()
            if self.current_index >= len(self.songs):
                self.current_index = 0
            print(f"✓ 已删除: {deleted['title']} - {deleted['artist']}")
        else:
            print("✗ 无效的索引")

    def reorder_song(self, from_idx, to_idx):
        if 0 <= from_idx < len(self.songs) and 0 <= to_idx < len(self.songs):
            song = self.songs.pop(from_idx)
            self.songs.insert(to_idx, song)
            self.save_playlist()
            print(f"✓ 已移动: {song['title']}")
        else:
            print("✗ 无效的索引")

    def shuffle_order(self):
        self.original_order = self.songs.copy()
        random.shuffle(self.songs)
        self.shuffle = True
        self.current_index = 0
        print("✓ 已打乱播放顺序")

    def restore_order(self):
        if self.original_order:
            self.songs = self.original_order
            self.original_order = []
            self.shuffle = False
            self.current_index = 0
            print("✓ 已恢复原始顺序")

    def optimize_order(self):
        styles = {}
        for song in self.songs:
            style = song['style']
            if style not in styles:
                styles[style] = []
            styles[style].append(song)

        optimized = []
        for style_songs in styles.values():
            optimized.extend(sorted(style_songs, key=lambda x: x['year']))

        self.songs = optimized
        self.save_playlist()
        print("✓ 已优化播放顺序（按风格分组，年份排序）")

    def play_current(self):
        song = self.get_current_song()
        search_term = f"{song['artist']} {song['title']}"
        audio_file = f"{MUSIC_DIR}/{self.current_index}.%(ext)s"

        print(f"\n🎵 正在播放: {song['title']} - {song['artist']}")
        print(f"   年份: {song['year']} | 风格: {song['style']}\n")

        local_file = None
        for ext in ['webm', 'mp3', 'm4a', 'flac']:
            path = f"{MUSIC_DIR}/{self.current_index}.{ext}"
            if os.path.exists(path):
                local_file = path
                break

        if not local_file:
            try:
                result = subprocess.run(
                    ['yt-dlp', '-f', 'bestaudio', '-o', audio_file, f'ytsearch1:{search_term}'],
                    capture_output=True, text=True, timeout=60
                )
                for ext in ['webm', 'mp3', 'm4a', 'flac']:
                    path = f"{MUSIC_DIR}/{self.current_index}.{ext}"
                    if os.path.exists(path):
                        local_file = path
                        break
            except Exception as e:
                print(f"下载失败: {e}")
                return False

        if local_file:
            subprocess.Popen(['ffplay', '-nodisp', '-autoexit', local_file],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False

    def next_song(self):
        self.current_index = (self.current_index + 1) % len(self.songs)
        return self.play_current()

    def prev_song(self):
        self.current_index = (self.current_index - 1 + len(self.songs)) % len(self.songs)
        return self.play_current()

    def play_all_continuous(self):
        while True:
            self.play_current()
            subprocess.run(['sleep', '3'])
            if not self.repeat_single:
                self.next_song()

def main():
    player = CantonesePlayer()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'play':
            player.play_current()
        elif cmd == 'next':
            player.next_song()
        elif cmd == 'prev':
            player.prev_song()
        elif cmd == 'list':
            player.show_playlist()
        elif cmd == 'optimize':
            player.optimize_order()
        elif cmd == 'shuffle':
            player.shuffle_order()
        elif cmd == 'restore':
            player.restore_order()
        else:
            print(f"未知命令: {cmd}")
    else:
        print(f"\n🎤 欢迎使用 {player.name}！\n")
        player.show_playlist()
        print("用法: python3 cantonese_manager.py [play|next|prev|list|optimize|shuffle|restore]")
        print("或直接运行 ./cantonese_player.sh 启动交互式播放\n")

if __name__ == '__main__':
    main()