@echo off

npx repomix --style markdown --remove-comments -i "output/,srt_files/,data/,**/system_instructions.yaml,**/song_list.json"

pause