#!/bin/bash

PLAYLIST_FILE="/Users/spark/pycharmproject/deva/playlist_cantonese.json"
MUSIC_DIR="/tmp/cantonese_music"
CURRENT_INDEX=0
TOTAL_SONGS=0

mkdir -p "$MUSIC_DIR"

show_menu() {
    echo "========================================"
    echo "     经典粤语老歌播放列表"
    echo "========================================"
    echo "当前播放: $(get_song_info "title") - $(get_song_info "artist")"
    echo "进度: $((CURRENT_INDEX + 1)) / $TOTAL_SONGS"
    echo "========================================"
    echo "1. 播放/暂停"
    echo "2. 下一首"
    echo "3. 上一首"
    echo "4. 显示列表"
    echo "5. 添加歌曲"
    echo "6. 删除当前歌曲"
    echo "7. 调整歌曲顺序"
    echo "8. 随机播放"
    echo "9. 单曲循环"
    echo "0. 退出"
    echo "========================================"
}

get_song_info() {
    local field=$1
    echo $(cat "$PLAYLIST_FILE" | jq -r ".songs[$CURRENT_INDEX].$field 2>/dev/null")
}

get_total() {
    echo $(cat "$PLAYLIST_FILE" | jq -r '.songs | length')
}

play_song() {
    local title=$(get_song_info "title")
    local artist=$(get_song_info "artist")
    local search_term="${artist} ${title}"
    local audio_file="${MUSIC_DIR}/${CURRENT_INDEX}.%(ext)s"

    echo "正在播放: $title - $artist"

    if [ -f "${MUSIC_DIR}/${CURRENT_INDEX}.webm" ] || [ -f "${MUSIC_DIR}/${CURRENT_INDEX}.mp3" ]; then
        echo "使用已下载文件..."
    else
        echo "正在搜索和下载..."
        yt-dlp -f bestaudio -o "${audio_file}" "ytsearch1:$search_term" > /dev/null 2>&1
    fi

    local file=$(ls ${MUSIC_DIR}/${CURRENT_INDEX}.* 2>/dev/null | head -1)
    if [ -n "$file" ]; then
        ffplay -nodisp -autoexit "$file" > /dev/null 2>&1 &
        FFPLAY_PID=$!
    fi
}

play_next() {
    killall ffplay 2>/dev/null
    CURRENT_INDEX=$(( (CURRENT_INDEX + 1) % TOTAL_SONGS ))
    play_song
}

play_prev() {
    killall ffplay 2>/dev/null
    CURRENT_INDEX=$(( (CURRENT_INDEX - 1 + TOTAL_SONGS) % TOTAL_SONGS ))
    play_song
}

show_playlist() {
    echo "========================================"
    echo "     播放列表 (共 $TOTAL_SONGS 首)"
    echo "========================================"
    cat "$PLAYLIST_FILE" | jq -r '.songs | to_entries[] | "\(.key + 1). \(.value.title) - \(.value.artist) [\( .value.year)] [\(.value.style)]"'
    echo "========================================"
}

add_song() {
    echo "请输入歌曲名:"
    read new_title
    echo "请输入歌手:"
    read new_artist
    echo "请输入年份:"
    read new_year
    echo "请输入风格:"
    read new_style

    local new_song="{\"title\": \"$new_title\", \"artist\": \"$new_artist\", \"year\": $new_year, \"style\": \"$new_style\"}"
    cat "$PLAYLIST_FILE" | jq ".songs += [$new_song]" > /tmp/playlist_tmp.json && mv /tmp/playlist_tmp.json "$PLAYLIST_FILE"
    TOTAL_SONGS=$(get_total)
    echo "已添加: $new_title - $new_artist"
}

delete_song() {
    if [ $TOTAL_SONGS -le 1 ]; then
        echo "列表只剩一首歌，无法删除"
        return
    fi
    cat "$PLAYLIST_FILE" | jq "del(.songs[$CURRENT_INDEX])" > /tmp/playlist_tmp.json && mv /tmp/playlist_tmp.json "$PLAYLIST_FILE"
    if [ $CURRENT_INDEX -ge $(get_total) ]; then
        CURRENT_INDEX=0
    fi
    TOTAL_SONGS=$(get_total)
    echo "已删除"
}

shuffle_play() {
    killall ffplay 2>/dev/null
    CURRENT_INDEX=$((RANDOM % TOTAL_SONGS))
    play_song
}

loop_single() {
    killall ffplay 2>/dev/null
    while true; do
        play_song
        wait $FFPLAY_PID
    done
}

TOTAL_SONGS=$(get_total)

if [ $# -eq 0 ]; then
    echo "欢迎使用经典粤语老歌播放列表!"
    echo "开始播放第1首: $(get_song_info "title") - $(get_song_info "artist")"
    play_song

    while true; do
        show_menu
        echo -n "请选择: "
        read choice

        case $choice in
            1) killall ffplay 2>/dev/null; play_song ;;
            2) play_next ;;
            3) play_prev ;;
            4) show_playlist ;;
            5) add_song ;;
            6) delete_song ;;
            7) echo "功能开发中..." ;;
            8) shuffle_play ;;
            9) loop_single ;;
            0) killall ffplay 2>/dev/null; echo "再见!"; exit 0 ;;
            *) echo "无效选择" ;;
        esac
    done
else
    case $1 in
        play) play_song ;;
        next) play_next ;;
        prev) play_prev ;;
        list) show_playlist ;;
        add) add_song ;;
        delete) delete_song ;;
        shuffle) shuffle_play ;;
        loop) loop_single ;;
        *) echo "用法: $0 {play|next|prev|list|add|delete|shuffle|loop}" ;;
    esac
fi