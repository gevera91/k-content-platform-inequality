# 보고서 원본과 PDF 빌드

`reports/kakao_enter.pdf`는 2026년 10월 27일 확정한 168쪽 최종 한국어 보고서다. 공개 패키지의 PDF는 최종 제출 파일과 바이트 단위로 같다. SHA-256은 `publication/report_provenance.json`과 릴리스의 체크섬에서 확인한다.

메인 소스는 저장소 루트의 `kakao_enter.tex`이며, 같은 위치의 스타일·부록과 `outputs/`, `docs/`의 그림을 사용한다. 원고의 기존 파일명과 상대 경로를 유지했다.

## 빌드 요건

- XeLaTeX, `latexmk`, `kpsewhich`
- 한국어 `kotex` 지원과 원고에 사용된 LaTeX 패키지
- TeX Live `unfonts-core`의 `UnBatang.ttf`, `UnBatangBold.ttf`, `UnDotum.ttf`, `UnDotumBold.ttf`

최종 보고서는 TeX Live 2024의 XeLaTeX로 작성·검증했다. 아래 도구는 `kpsewhich`로 설치된 한글 글꼴 위치를 찾고, 임시 소스에만 그 위치를 적용한다. 개인 컴퓨터의 특정 폴더를 만들 필요가 없다.

```bash
python3 scripts/build_report_portable.py --check-only
python3 scripts/build_report_portable.py
```

글꼴을 별도 폴더에 설치했다면 `--font-dir /path/to/unfonts-core`를 지정한다. 새 PDF는 무시된 작업 폴더 `build/kakao_enter.pdf`에 생성된다. 공개 릴리스의 확정 PDF는 덮어쓰지 않는다. TeX·폰트 버전에 따라 페이지 배치와 PDF 바이트가 달라질 수 있으므로, 원문 확인에는 함께 배포한 확정 PDF를 사용한다.
