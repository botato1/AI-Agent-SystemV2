#!/usr/bin/env bash
cd "$(dirname "$0")/.."

python sweep_speaker_floor.py --meeting ded1105f-6bcd-43fe-8f1f-b7e861b71ade_20260805-081801 --script scripts/launch_plan_meeting.txt --names 문지수 김나연 이승주 가동현 --holdout 가동현 --floors 0.35 0.40 0.45

python sweep_speaker_floor.py --meeting ba8f38c4-2eba-4049-ae1d-a0f66533e131_20260812-062851 --script scripts/search_quality_meeting.txt --names 문지수 김나연 이승주 이준오 --holdout 이준오 --floors 0.35 0.40 0.45

python sweep_speaker_floor.py --meeting 8b5f84b7-5e29-46f5-bb67-158980a5f352_20260805-064739 --script scripts/retention_meeting.txt --names 문지수 김나연 이승주 이준오 가동현 --holdout 이준오 --floors 0.35 0.40 0.45
