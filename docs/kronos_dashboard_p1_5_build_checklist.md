# Kronos 웹 대시보드 P1.5 단계 빌드/운영 체크리스트

**작성일**: 2026-05-13 KST  
**상태**: P1.5 사전 운영 체크리스트 (학습 진행 중, 구현 미진행)  
**대상**: P1.5 PR 시작 전 필수 확인 항목  

---

## 경고: 이 체크리스트를 따르지 않으면 P1.5 PR이 ralplan 합의 결정(REV-1, REV-2, REV-7, B-1, AC-1)을 위반할 수 있습니다.

---

## 1. P1.5 시작 전 사전 조건 (GO/NOGO)

모두 GO여야 P1.5 PR 시작. **하나라도 NOGO면 P1 SSR 유지 + 사유 docs commit.**

| # | 조건 | 확인 명령 | GO 기준 | 상태 |
|---|---|---|---|---|
| 1 | predictor 학습 완료 | PowerShell: `Invoke-RestMethod -Uri 'http://127.0.0.1:7070/api/training/status' \| Select-Object @{n='stage';e={$_.latest_stage.train_stage}}, @{n='status';e={$_.status}}` | `train_stage=predictor`, `status=completed` | ☐ |
| 2 | readiness.predictor_complete | 동일 API 응답 `readiness.predictor_complete` 필드 | `true` | ☐ |
| 3 | checkpoint 파일 ≥ 1개 | `Invoke-RestMethod -Uri 'http://127.0.0.1:7070/api/training/artifacts' \| Select-Object -ExpandProperty predictor \| Select-Object checkpoint_file_count` | `checkpoint_file_count ≥ 1` | ☐ |
| 4 | model_weight 파일 ≥ 1개 | 동일 API 응답 `model_weight_file_count` | `≥ 1` | ☐ |
| 5 | 학습 프로세스 종료 | PowerShell: `Get-Process python \| Where-Object {$_.ProcessName -match 'python'} \| Measure-Object` | tokenizer/predictor 관련 python 프로세스 개수 = 0 | ☐ |
| 6 | GPU VRAM 해제 | `Invoke-RestMethod -Uri 'http://127.0.0.1:7070/api/training/gpu' \| Select-Object total_memory_used_percent` | `total_memory_used_percent < 5` | ☐ |
| 7 | 디스크 I/O 안정 | PowerShell: `Get-Counter '\PhysicalDisk(_Total)\% Disk Time' -SampleInterval 1 -MaxSamples 60 \| Select-Object -ExpandProperty CounterSamples \| Measure-Object -Property CookedValue -Average` | 평균 < 5% | ☐ |

**GO/NOGO 판정**: 7개 항목 모두 ☑ 확인 → P1.5 시작 허가  
**NOGO 시**: 각 항목별 실패 사유를 정리해 `docs/p1_5_nogo_reason.md` commit (예: "predictor 학습 중단됨 — 메모리 부족", "checkpoint 0개 — 정상 경로 아님" 등)

---

## 2. Disk Baseline 매트릭스 측정 (B-1 의무)

**목적**: `npm ci` 실행 전후의 디스크 I/O 변화를 정량화하여 학습 중 npm 영향 검증.  
**산출물**: `docs/p1_5_disk_baseline.md` (본 체크리스트와 별도 파일로 기록)

### PowerShell 명령 스니펫

```powershell
# === BASELINE 측정 (npm install 전, ~5분) ===
Write-Output "=== BASELINE START ==="
$baseline = @()
for ($i = 1; $i -le 60; $i++) {
  $counter = Get-Counter '\PhysicalDisk(_Total)\% Disk Time' -SampleInterval 5
  $value = $counter.CounterSamples[0].CookedValue
  $baseline += $value
  Write-Output "Sample $i : $value %"
  Start-Sleep -Seconds 1
}
$baseline_avg = ($baseline | Measure-Object -Average).Average
Write-Output "BASELINE AVERAGE: $baseline_avg %"

# === npm ci 실행 (동시 모니터링) ===
Write-Output "=== npm ci START ==="
$install_baseline = @()
$jobParams = @{
  ScriptBlock = {
    param($path)
    Set-Location $path
    npm ci --prefer-offline --no-audit --no-fund
  }
  ArgumentList = 'D:\Chanil_Park\Project\Programming\Kronos\webui\v2_src'
  Name = 'npm_ci_job'
}
$npmJob = Start-Job @jobParams

# npm ci 중 디스크 I/O 수집 (최대 10분)
$installMonitoring = @()
for ($i = 1; $i -le 120; $i++) {
  if ((Get-Job -Name 'npm_ci_job' -ErrorAction SilentlyContinue).State -eq 'Completed') {
    Write-Output "npm ci completed at sample $i"
    break
  }
  $counter = Get-Counter '\PhysicalDisk(_Total)\% Disk Time' -SampleInterval 3
  $value = $counter.CounterSamples[0].CookedValue
  $installMonitoring += $value
  Write-Output "npm install sample $i : $value %"
  Start-Sleep -Seconds 2
}
$install_avg = ($installMonitoring | Measure-Object -Average).Average
Write-Output "INSTALL MONITORING AVERAGE: $install_avg %"

# npm ci 결과 대기 및 확인
Receive-Job -Name 'npm_ci_job' -Wait -ErrorAction SilentlyContinue
$npmJobStatus = (Get-Job -Name 'npm_ci_job').State
Write-Output "npm ci status: $npmJobStatus"

# === POST-INSTALL 측정 (~5분) ===
Write-Output "=== POST-INSTALL BASELINE ==="
$post = @()
for ($i = 1; $i -le 60; $i++) {
  $counter = Get-Counter '\PhysicalDisk(_Total)\% Disk Time' -SampleInterval 5
  $value = $counter.CounterSamples[0].CookedValue
  $post += $value
  Write-Output "Sample $i : $value %"
  Start-Sleep -Seconds 1
}
$post_avg = ($post | Measure-Object -Average).Average
Write-Output "POST-INSTALL AVERAGE: $post_avg %"

# === 결과 정리 ===
$diff_pct = [math]::Abs(($install_avg - $baseline_avg) / $baseline_avg) * 100
Write-Output ""
Write-Output "SUMMARY"
Write-Output "======="
Write-Output "Baseline avg       : $([math]::Round($baseline_avg, 2)) %"
Write-Output "Install avg        : $([math]::Round($install_avg, 2)) %"
Write-Output "Post-install avg   : $([math]::Round($post_avg, 2)) %"
Write-Output "Diff (install/baseline) : $([math]::Round($diff_pct, 2)) %"
Write-Output "ACCEPTANCE: diff ±5% = $($diff_pct -le 5 ? 'PASS' : 'FAIL')"
```

### Acceptance 기준 (B-1)

- **baseline 평균** vs **install 중 평균** 차이: **±5% 이내**
- 이유: 학습 종료 후 측정이므로 통상 통과. 초과 시 → npm ci를 낮은 우선순위 + `--prefer-offline --no-audit --no-fund` 로 재실행

### 산출물 저장 위치

`docs/p1_5_disk_baseline.md` (신규 파일):

```markdown
# P1.5 npm ci 디스크 I/O 베이스라인

측정 일시: 2026-05-XX 14:30 KST
측정 환경: Windows 11 Pro, RTX 4080 SUPER (GPU 유휴), predictor 완료 후

| 단계 | 평균 디스크 I/O | 표본 수 | 시간 |
|------|---|---|---|
| Baseline (npm 전) | XX.XX % | 60 | 5분 |
| npm ci 실행 중 | YY.YY % | 120 | 10분 |
| Post-install | ZZ.ZZ % | 60 | 5분 |

**차이**: |YY.YY - XX.XX| / XX.XX = AA% (수용 여부: ±5% 이내)

**결론**: PASS / FAIL

명령 기록: [위 스니펫]
```

---

## 3. Stack 재평가 체크리스트 (lock-in 방지)

**목적**: ralplan 합의 시점(2026-05-12)의 버전 가정을 P1.5 PR 시작 시점(예상 2026-07-01경)에 재확인.

| 항목 | 합의 시점 가정 | 재평가 항목 | GO 기준 | 의사결정 |
|---|---|---|---|---|
| **Svelte** | 5.x | 메이저 6 출시 여부? | 6 미출시: 5.x 유지 / 6 출시: 6 채택 또는 5 LTS 유지 사유 문서화 | ☐ |
| **Vite** | 5.x | 메이저 6 출시 여부? | 6 미출시: 5.x 유지 / 6 출시: 호환성 확인 후 6 또는 5 유지 | ☐ |
| **Node.js** | 20 LTS | 22 LTS 이동 필요? | 20/22 모두 LTS면 22 권장, 사유 문서화. 22 미출시면 20 유지 | ☐ |
| **Tailwind CSS** | 3.x | 메이저 4 stable 출시? | 4 미출시: 3.x 유지 / 4 stable: 4 채택 (Play CDN 금지) | ☐ |
| **Apache ECharts** | 5.5 | 메이저 6 출시 여부? | 6 미출시: 5.x 유지 / 6 stable: 호환성 확인 후 업그레이드 검토 | ☐ |
| **Plotly.js** | 2.35 | 메이저 3 출시 여부? | 3 미출시: 2.35 유지 / 3 stable: breaking change 검토 후 결정 | ☐ |
| **TypeScript** | 5.x | 메이저 6 출시 여부? | 6 미출시: 5.x 유지 / 6 stable: 호환성 확인 후 업그레이드 | ☐ |

### 반영 방식

각 결정사항을 다음 파일에 기록:

1. **`webui/v2_src/package.json`**:
   - `engines.node: "^20"` (Node 20 LTS pin)
   - `engines.npm: "^9"` (npm 9.x 이상)
   - 각 의존성: `"svelte": "^5.0.0"`, `"vite": "^5.0.0"` 등 (semver `^x.y.0`)

2. **`webui/v2_src/package-lock.json`**:
   - `npm ci` 실행으로 자동 생성 후 **commit** (재현성 보장)

3. **차이점 발생 시**: `docs/p1_5_stack_decisions.md` 추가 파일로 버전 변경 사유 문서화

---

## 4. Build Artifact Policy (REV-7 확정)

### .gitignore 설정

`webui/v2_src/.gitignore` (신규 작성):

```gitignore
# Dependencies (npm install이 생성)
node_modules/

# Build cache
.vite/
.vite-cache/

# Logs
*.log
npm-debug.log*
yarn-debug.log*

# Environment
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# macOS
.DS_Store
```

### Commit 정책

| 파일/디렉터리 | 커밋 대상 | 이유 |
|---|---|---|
| `webui/v2_src/src/**` | ✅ YES | 소스 코드 |
| `webui/v2_src/package.json` | ✅ YES | 의존성 선언 |
| `webui/v2_src/package-lock.json` | ✅ YES | 의존성 lock (재현성) |
| `webui/v2_src/vite.config.ts` | ✅ YES | 빌드 설정 |
| `webui/v2_src/tsconfig.json` | ✅ YES | TypeScript 설정 |
| `webui/v2_src/tailwind.config.js` | ✅ YES | Tailwind 설정 |
| `webui/v2_src/postcss.config.js` | ✅ YES | PostCSS 설정 |
| `webui/v2_src/index.html` | ✅ YES | HTML 진입점 |
| **`webui/static/v2/dist/**`** | ✅ YES | **빌드 산출물 (prebuilt 정책)** |
| `webui/v2_src/node_modules/**` | ❌ NO | .gitignore (대용량, 재현 가능) |
| `webui/v2_src/.vite-cache/**` | ❌ NO | .gitignore (빌드 캐시) |

### dist 폴더를 commit하는 이유

1. **학습 머신은 빌드 환경이 아님**: Python 위주 개발. Node.js/npm 설치 미배경 가능성
2. **P6 cutover 시 504 방지**: Flask static 경로가 빌드 산출물 없으면 404 → 시스템 다운
3. **결정적 빌드**: Vite 빌드는 동일 소스/lock → 동일 산출물 보장 가능
4. **시간 절감**: 배포 시 재빌드 불필요, Flask가 바로 정적 서빙

### 실행 방법

```powershell
# 학습 완료 후, 별도 깨끗한 환경에서
cd D:\Chanil_Park\Project\Programming\Kronos\webui\v2_src

# 1. 의존성 설치 (lock 기반)
npm ci --prefer-offline --no-audit --no-fund

# 2. 빌드
npm run build

# 3. 산출물 확인
ls webui/static/v2/dist/index.html  # 존재해야 함

# 4. commit
git add webui/v2_src/src webui/v2_src/package.json webui/v2_src/package-lock.json webui/v2_src/vite.config.ts webui/v2_src/tsconfig.json webui/v2_src/tailwind.config.js webui/v2_src/postcss.config.js webui/v2_src/index.html
git add webui/static/v2/dist/

git commit -m "feat(webui-v2): Vite+Svelte SPA 빌드 산출물 추가 (prebuilt 정책)"
```

---

## 5. npm install Protocol (필수 사항)

### 반드시 `npm ci` 사용 (npm install 금지)

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos\webui\v2_src

# ✅ 올바른 방법: package-lock.json 강제 준수
npm ci --prefer-offline --no-audit --no-fund

# ❌ 금지된 방법: lock 파일 무시 가능성
npm install
```

### 이유

- `npm ci`: `package-lock.json` **강제** 준수 (완전 재현성)
- `npm install`: lock 파일을 무시할 수 있음 (버전 변동 위험)
- `--prefer-offline`: 캐시 우선 사용, 네트워크 호출 감소
- `--no-audit`: 취약점 스캔 비활성화 (네트워크 호출 감소)
- `--no-fund`: 펀딩 정보 조회 비활성화 (네트워크 호출 감소)

### 최초 lockfile 생성 (1회 예외)

```powershell
# package-lock.json이 아직 없을 때만
npm install --package-lock-only

# 그 후 lock 파일 commit
git add package-lock.json
git commit -m "P1.5 의존성 lockfile을 고정하다"
```

---

## 6. Vite 빌드 설정 및 SSR Marker 보존 (B-2, REV-2)

### `webui/v2_src/vite.config.ts` 필수 설정

```typescript
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  base: '/static/v2/dist/',  // Flask static 매핑
  plugins: [svelte()],
  build: {
    outDir: '../static/v2/dist',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          // Plotly는 STOM 탭만 필요하므로 lazy chunk로 분리
          plotly: ['plotly.js-dist-min'],
        },
      },
    },
  },
  server: {
    port: 5173,
    watch: {
      // 학습 디렉터리 제외 (파일 변화 폭주 방지)
      ignored: [
        '**/finetune/outputs/**',
        '**/_database/**',
        '**/checkpoints/**',
        '**/logs/**',
        '**/webui/prediction_results/**',
        '**/webui/stom_predictions/**',
        '**/*.db',
      ],
    },
  },
});
```

### `webui/v2_src/index.html` SSR Marker 정적 박기 (B-2)

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <!-- [B-2 SSR Marker] 정적 문자열로 박혀 있어 grep 검증 가능 -->
  <meta name="kronos-v2-shell" content="hero,live-training,stom,forecast,artifacts,history,system-health">
  <meta name="kronos-v2-version" content="p1-5-spa">
  <title>Kronos 통합 대시보드</title>
  <link rel="icon" type="image/svg+xml" href="/vite.svg" />
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
```

### 빌드 후 Marker 검증 (B-2)

```powershell
# 빌드 실행
npm run build

# SSR marker가 빌드 산출물에 유지되는지 확인
Select-String -Path 'webui/static/v2/dist/index.html' -Pattern 'kronos-v2-shell'
# 결과: 매치되어야 함 (0 matches = FAIL)

Select-String -Path 'webui/static/v2/dist/index.html' -Pattern 'kronos-v2-version'
# 결과: 매치되어야 함
```

### 자동 테스트 추가 (Python, P1.5 이후 pytest)

`tests/test_v2_dist_marker.py` (신규):

```python
import os
import pytest

def test_dist_marker_preserved_after_build():
    """[B-2] SSR marker가 Vite 빌드 후에도 보존됨"""
    dist_index = 'webui/static/v2/dist/index.html'
    
    if not os.path.exists(dist_index):
        pytest.skip("P1.5 dist not built yet")
    
    with open(dist_index, 'r', encoding='utf-8') as f:
        body = f.read()
    
    assert 'kronos-v2-shell' in body, "SSR marker 'kronos-v2-shell' not found in dist/index.html"
    assert 'kronos-v2-version' in body, "SSR marker 'kronos-v2-version' not found in dist/index.html"
    assert 'p1-5-spa' in body, "Version string 'p1-5-spa' not found in dist/index.html"
```

---

## 7. Flask Blueprint 및 dist 모드 활성화

### `webui/v2/__init__.py` Blueprint (이미 P1에서 생성됨)

```python
from flask import Blueprint, render_template, send_from_directory, current_app
import os

v2_bp = Blueprint('v2', __name__)

@v2_bp.route('/v2')
def v2_index():
    """
    P1.5: dist 모드 활성화 시 Vite 빌드 산출물 서빙.
    KRONOS_V2_DIST=0 또는 파일 미존재 시 P1 SSR Jinja 폴백.
    """
    dist_index = os.path.join(current_app.static_folder, 'v2', 'dist', 'index.html')
    
    if (os.path.exists(dist_index) and 
        os.environ.get('KRONOS_V2_DIST', '0') == '1'):
        return send_from_directory(
            os.path.join(current_app.static_folder, 'v2', 'dist'),
            'index.html',
        )
    
    # P1 폴백: SSR Jinja
    return render_template('v2_shell.html')

@v2_bp.route('/v2/<path:subpath>')
def v2_spa_fallback(subpath):
    """
    [REV-2] v2 prefix 내부 catch-all만 허용.
    글로벌 /<path:p> 금지.
    """
    return v2_index()
```

### dist 모드 활성화 명령

```powershell
# 환경변수 설정
$env:KRONOS_V2_DIST = "1"

# Flask 앱 재시작 (또는 재실행)
python -m webui.run
# 또는
$env:FLASK_APP = "webui.app:app"
flask run --host=127.0.0.1 --port=7070
```

### 활성화 후 검증

```powershell
# 1. dist/index.html 반환 확인
$response = Invoke-WebRequest -Uri 'http://127.0.0.1:7070/v2'
$response.StatusCode  # 200이어야 함

# 2. SSR marker 포함 확인
if ($response.Content -match 'kronos-v2-version.*p1-5-spa') {
  Write-Output "✓ SSR marker verified"
} else {
  Write-Output "✗ SSR marker NOT found"
}

# 3. 정적 자산 로드 확인
Invoke-WebRequest -Uri 'http://127.0.0.1:7070/static/v2/dist/assets/'
# 200 OK + JavaScript/CSS 파일 목록
```

---

## 8. Rollback 절차 (P1.5 머지 후 문제 발생 시)

### 즉시 Rollback (1초)

```powershell
# 환경변수 비활성화 → P1 SSR 자동 폴백
$env:KRONOS_V2_DIST = "0"

# Flask 재시작
Restart-Service -Name 'KronosFlask' -Force  # 또는 수동 재시작
# 또는
# 프로세스 종료 후 다시 실행
```

### 영구 Rollback (코드)

```powershell
# 옵션 1: dist 파일 삭제 (Blueprint가 파일 미존재 감지 → P1 폴백)
Remove-Item -Path 'webui/static/v2/dist/' -Recurse -Force

# 옵션 2: 커밋 되돌리기
git revert <P1.5-commit-hash>

# 둘 다 실행 후 Flask 재시작
```

### 추가 안전망 (B-5)

Plan §4의 4가지 rollback trigger 중 하나라도 만족 시 즉시 롤백:

| 트리거 | 기준 | 모니터링 방법 |
|---|---|---|
| readiness 오분류 | 1회 발견 | `/api/training/status` 응답 모니터링 |
| p95 API latency | > 500ms (baseline 대비 +50%) | Flask/Gunicorn 로그 또는 APM |
| error rate | > 1% (5분 윈도우) | Flask error 로그 수집 |
| critical bug | 1건 보고 | 사용자 피드백 |

---

## 9. P1.5 PR 작업 순서 (실제 진행 시 따를 절차)

| 단계 | 작업 | 검증 |
|---|---|---|
| **1. 사전 조건 확인** | §1 GO/NOGO 표 7개 항목 모두 확인 | 모두 ☑ 또는 NOGO 사유 문서화 |
| **2. Disk baseline 측정** | §2 PowerShell 스니펫 실행, `docs/p1_5_disk_baseline.md` 저장 | ±5% 이내 acceptance |
| **3. Stack 재평가** | §3 표 7개 항목 버전 확인, 변경 사항 문서화 | `package.json` `engines` 필드 업데이트 |
| **4. `webui/v2_src/` 초기화** | `npm init -y` + 의존성 설치 (svelte, vite, typescript, tailwindcss, echarts, plotly 등) | `npm ci --prefer-offline` 성공 |
| **5. 설정 파일 작성** | vite.config.ts, tsconfig.json, tailwind.config.js, postcss.config.js, index.html (SSR marker 포함) | 파일 생성 확인 |
| **6. 컴포넌트 작성** | design_spec.md 따라 src/lib/theme.ts, src/components/*.svelte | 타입체크 무에러 |
| **7. 빌드** | `npm run build` | `webui/static/v2/dist/` 생성 |
| **8. SSR marker 검증** | §6 `Select-String` 명령 실행 | marker 2개 발견 |
| **9. KRONOS_V2_DIST=1 활성화** | 환경변수 설정 + Flask 재시작 | `http://127.0.0.1:7070/v2` 정상 로드 |
| **10. pytest 통과** | 기존 17개 + 신규 `test_v2_dist_marker.py` | 모두 PASS |
| **11. Lighthouse 측정** | §13 Flask production-mode 측정 | a11y ≥ 90, performance ≥ 80 |
| **12. Commit + PR** | 단계별 분할 PR (PR-1~PR-5) | 각 PR 리뷰 통과 |

---

## 10. PR 분할 전략 (대량 변경 회피)

P1.5는 하나의 거대 PR이 아니라 **5개 단계 PR**로 분할:

| PR | 내용 | 파일 | 의존성 | commit msg |
|---|---|---|---|---|
| **PR-1** | 의존성 + 설정 | `package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `postcss.config.js`, `index.html` (SSR marker 박음) | 선행 없음 | `build(webui-v2): npm 의존성 및 Vite 설정 추가` |
| **PR-2** | 유틸 + 테마 | `src/lib/theme.ts`, `src/lib/api.ts`, `src/stores/*.ts`, `src/utils/*.ts` | PR-1 필수 | `feat(webui-v2): 공유 theme/api/stores 구현` |
| **PR-3** | 레이아웃 | `src/App.svelte`, `src/components/Layout.svelte`, `src/components/Sidebar.svelte`, `src/components/HeroStrip.svelte` | PR-2 필수 | `feat(webui-v2): 레이아웃 및 네비게이션 구축` |
| **PR-4** | 컴포넌트 | `src/routes/LiveTraining.svelte`, `src/components/{StageStepper,LossChart,EtaTimeline,GpuSparkline}.svelte` (W1~W5, W7) | PR-3 필수 | `feat(webui-v2): live training 컴포넌트 구현` |
| **PR-5** | 빌드 + 배포 | `webui/static/v2/dist/**`, `KRONOS_V2_DIST=1` 활성화 | PR-4 필수 | `feat(webui-v2): Vite 빌드 산출물 및 dist 모드 활성화` |

각 PR은 **독립적으로 P1 SSR 폴백 가능** (`KRONOS_V2_DIST=0` 또는 파일 미존재 → P1 Jinja 자동 사용).

---

## 11. Lighthouse 측정 환경 (B-5, P1.5 성능 기준)

### 측정 준비

```powershell
# Flask production 모드 설정
$env:FLASK_ENV = "production"
$env:KRONOS_V2_DIST = "1"

# Gunicorn 또는 waitress로 gzip 활성화
# (waitress는 기본 gzip 비활성, 별도 middleware 필요)
python -m waitress --listen=127.0.0.1:7070 webui.app:app
```

### Lighthouse 명령

```powershell
# npm이 설치된 머신에서 실행
npx lighthouse `
  http://127.0.0.1:7070/v2 `
  --output=json `
  --output-path=docs/lighthouse_v2_p1_5.json `
  --chrome-flags="--headless=new --no-sandbox --disable-gpu" `
  --only-categories=performance,accessibility `
  --throttling-method=simulate
```

### Acceptance 기준 (B-5)

| 카테고리 | 최소값 | 측정 대상 |
|---|---|---|
| Accessibility | ≥ 90 | 접근성 준수 (스크린 리더, 키보드 네비) |
| Performance | ≥ 80 | 첫 페인트, LCP, CLS 등 |

---

## 12. 위반 시 책임 매트릭스

| 위반 사항 | 결과 | 복구 방법 |
|---|---|---|
| **학습 중 npm install 실행** | D1 위반 — 즉시 중단, 학습 영향 측정, docs commit | `docs/incident_npm_during_training.md` 작성 후 재진행 |
| **dist commit 누락** | P6 cutover 시 404 — rollback | git history 수정 또는 별도 "dist 추가" commit |
| **SSR marker 누락** | smoke test FAIL → PR 머지 차단 | `index.html`에 `<meta>` 태그 추가 후 재빌드 |
| **`package-lock.json` commit 누락** | 재현성 깨짐 → 다른 환경에서 빌드 불일치 | lock 파일 생성 후 commit, `npm ci` 재실행 |
| **글로벌 catch-all 라우트 추가** | 라우팅 충돌 — REV-2 위반 → PR 머지 차단 | Blueprint 검토, 기존 라우트와 충돌 제거 |
| **Play CDN 또는 dev asset 포함** | AC-1 위반 — prod 빌드 불안정 → rollback | `vite.config.ts` 빌드 설정 검토, dist 재빌드 |

---

## 13. 최종 확인 항목

P1.5 PR 머지 직전 마지막 체크:

- [ ] §1 GO/NOGO 7개 항목 모두 ☑
- [ ] §2 Disk baseline `docs/p1_5_disk_baseline.md` 작성 완료
- [ ] §3 Stack 재평가 `package.json` 버전 확정
- [ ] §4 `.gitignore` 작성, dist/ + src/ commit, node_modules 제외
- [ ] §5 `npm ci` (npm install 아님) 실행 및 lock 파일 commit
- [ ] §6 `index.html` SSR marker 정적 박음 확인
- [ ] §6 빌드 후 marker `Select-String` 검증 통과
- [ ] §7 Blueprint 기존 라우트와 충돌 없음 확인 (`app.url_map` 비교)
- [ ] §8 Rollback 절차 문서화 완료
- [ ] §10 PR 분할 계획 5개 PR 준비
- [ ] §11 Lighthouse 측정 환경 구성, a11y ≥ 90, performance ≥ 80
- [ ] 기존 pytest 17개 + 신규 `test_v2_dist_marker.py` 모두 PASS
- [ ] `git status --short --branch` clean 확인
- [ ] commit message [ralplan 합의](#합의-결정) 반영 여부 확인

---

## 합의 결정

이 체크리스트는 다음 ralplan 합의 결정을 **운영 수준에서 실행**하기 위해 작성되었습니다:

| 결정 ID | 내용 | 본 체크리스트 반영 |
|---|---|---|
| **B-1** | P1/P1.5 분리: 학습 중 npm 0, predictor 완료 후 npm ci | §1, §2, §5, §9 |
| **B-2** | SSR marker: server-side `<meta>` grep 검증 | §6, §8 테스트 |
| **B-5** | Rollback trigger: 정량화 (readiness/latency/error/bug) | §8, §11 |
| **REV-2** | vite.config 설정: `server.watch.ignored` 학습 디렉터리 제외 | §6 |
| **REV-7** | dist commit: prebuilt 정책, node_modules 제외 | §4 |
| **AC-1** | Tailwind prebuilt: Play CDN 금지 | §6, §12 |

---

## 상태

**상태**: P1.5 사전 운영 체크리스트 (predictor 완료 후 PR로 적용)

predictor 학습이 완료되면 이 체크리스트의 §1~§13을 순서대로 따르고, 각 단계마다 체크박스(☐/☑)를 기록하여 추적하세요.
