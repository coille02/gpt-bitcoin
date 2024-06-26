<<<<<<< Updated upstream
# OpenAI GPT-4를 활용한 업비트 자동매매 시스템 

이 프로젝트는 OpenAI GPT-4 API를 활용하여 업비트 자동매매 시스템을 구현한 것입니다. 
기존의 유튜버 조코딩님의 소스 코드(<https://github.com/youtube-jocoding/gpt-bitcoin.git>)를 기반으로 수정 및 개선하였습니다.

## 관련 링크
- [조코딩님의 수업 자료](https://jocoding.net/bitcoin)
- [조코딩님의 라이브 풀버전 링크(멤버십 전용)](https://youtube.com/live/-7IVgjUw79s?feature=share)
- 편집본 (업데이트 예정)

## 로컬 환경 설정
```pip install -r requirements.txt```


## AWS EC2 Ubuntu 서버 설정 방법
### 업비트 API 허용 IP 설정
[업비트 API 홈페이지](https://upbit.com/mypage/open_api_management)

### 기본 세팅
- 한국 기준으로 서버 시간 설정
```
sudo ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime
```

- 패키지 목록 업데이트
```
sudo apt update
```

- 패키지 목록 업그레이드
```
sudo apt upgrade
```

- pip3 설치
```
sudo apt install python3-pip
```

### 레포지토리 가져오기
```
git clone https://github.com/coille02/gpt-bitcoin.git
```

### 서버에서 라이브러리 설치
```
pip3 install -r requirements.txt
```

### .env 파일 만들고 API KEY 넣기
```
vim .env
```
### 명령어
- 현재 경로 상세 출력
```
ls -al
```

- 경로 이동
```
cd 경로
```

- vim 에디터로 파일 열기
```
vim autotrade.py
```

- vim 에디터 입력: i
- vim 에디터 저장: ESC + wq!

### 실행하기
- 그냥 실행
```
python3 autotrade.py
```

- 백그라운드 실행
```
nohup python3 -u autotrade.py > output.log 2>&1 &
```

- 로그 보기
```
cat output.log
tail -f output.log
```

- 실행 확인
```
ps ax | grep .py
```

- 종료하기
```
kill -9 PID
ex. kill -9 13586
=======
# OpenAI GPT-4를 활용한 업비트 자동매매 시스템 

이 프로젝트는 OpenAI GPT-4 API를 활용하여 업비트 자동매매 시스템을 구현한 것입니다. 
기존의 유튜버 조코딩님의 소스 코드(<https://github.com/youtube-jocoding/gpt-bitcoin.git>)를 기반으로 수정 및 개선하였습니다.

## 관련 링크
- [조코딩님의 수업 자료](https://jocoding.net/bitcoin)
- [조코딩님의 라이브 풀버전 링크(멤버십 전용)](https://youtube.com/live/-7IVgjUw79s?feature=share)
- 편집본 (업데이트 예정)

## 로컬 환경 설정
```pip install -r requirements.txt```


## AWS EC2 Ubuntu 서버 설정 방법
### 업비트 API 허용 IP 설정
[업비트 API 홈페이지](https://upbit.com/mypage/open_api_management)

### 기본 세팅
- 한국 기준으로 서버 시간 설정
```
sudo ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime
```

- 패키지 목록 업데이트
```
sudo apt update
```

- 패키지 목록 업그레이드
```
sudo apt upgrade
```

- pip3 설치
```
sudo apt install python3-pip
```

### 레포지토리 가져오기
```
git clone https://github.com/coille02/gpt-bitcoin.git
```

### 서버에서 라이브러리 설치
```
pip3 install -r requirements.txt
```

### .env 파일 만들고 API KEY 넣기
```
vim .env
```
### 명령어
- 현재 경로 상세 출력
```
ls -al
```

- 경로 이동
```
cd 경로
```

- vim 에디터로 파일 열기
```
vim autotrade.py
```

- vim 에디터 입력: i
- vim 에디터 저장: ESC + wq!

### 실행하기
- 그냥 실행
```
python3 autotrade.py
```

- 백그라운드 실행
```
nohup python3 -u autotrade.py > output.log 2>&1 &
```

- 로그 보기
```
cat output.log
tail -f output.log
```

- 실행 확인
```
ps ax | grep .py
```

- 종료하기
```
kill -9 PID
ex. kill -9 13586
>>>>>>> Stashed changes
```