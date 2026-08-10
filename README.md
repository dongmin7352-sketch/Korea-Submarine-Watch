# 🇰🇷 Korea Submarine Watch

한화오션·HD현대중공업의 잠수함 수출/건조/기술 관련 뉴스를 매일 자동으로 추적하는 대시보드입니다.
(Saudi Submarine Watch와 동일한 구조 — Google News RSS 수집 + GitHub Actions 자동화 + GitHub Pages 배포)

## 하는 일

- 국내(연합뉴스, 조선비즈 등)와 해외 방산매체(Naval News, Defense News, Janes 등)를 Google News RSS로 모니터링
- 한화오션 / HD현대중공업 + 잠수함 키워드가 함께 언급된 기사만 필터링
- 중복 제거, 관련도 스코어링, 도입 단계(검토/입찰/계약/건조/인도 등) 분류
- OpenAI API가 있으면 한국어 요약·중요도 평가, 없으면 규칙 기반 폴백 사용
- GitHub Actions로 매일(한국시간 08:00) 자동 실행 → GitHub Pages에 자동 배포

## 1. 레포지토리에 업로드

이 폴더의 모든 파일/폴더를 GitHub 레포지토리에 그대로 올리세요.

## 2. GitHub Pages 활성화

Repository → Settings → Pages → **Source**를 **GitHub Actions**로 설정

## 3. (선택) AI 요약 활성화

Repository → Settings → Secrets and variables → Actions → New repository secret

- Name: `OPENAI_API_KEY`
- Value: OpenAI API 키

키가 없어도 동작하며, 이 경우 규칙 기반 요약/중요도로 대체됩니다.

## 4. 수동 실행

Repository → Actions → **Update Korea Submarine Watch** → Run workflow

스케줄 실행은 매일 23:00 UTC(한국시간 08:00)에 자동으로 돌아갑니다 (다소 지연될 수 있음).

## 모니터링 소스

- 한화오션 관련 (국내, Google News 한국어판)
- HD현대중공업 관련 (국내)
- 국내 잠수함 수출 종합 검색
- 연합뉴스, 조선비즈 (site: 제한)
- Naval News, Defense News, Naval Technology, Breaking Defense, Janes (해외)
- Google News 종합(영문)

소스 목록은 `scripts/update_news.py`의 `SOURCES`에서 수정할 수 있습니다.

## 진단 로그

수집이 잘 안 될 때는 `.github/workflows/update.yml`의 `DEBUG_COLLECTOR: "1"` 주석을 해제하고
다시 실행하면, 소스별 raw/필터 통과 개수와 점수 미달로 제외된 기사 목록이 Actions 로그에 출력됩니다.

## 중요

이 사이트는 뉴스 모니터링 도구이며 조달/계약 확정을 의미하지 않습니다.
중요한 내용은 반드시 원문 기사와 공식 발표로 재확인하세요.
