# Model Bridge MCP 개선 로드맵

> 생성일: 2026-02-12
> 최종 업데이트: 2026-02-15
> 상태: **P1~P3 전체 완료**

---

## 1. 완료된 개선 항목

### ✅ P1 - Foundation (기반 구축)

| 항목 | 완료일 | 주요 내용 |
|------|--------|----------|
| **P1-1: Provider Registry 확장** | 2026-02-12 | Capability negotiation, 동적 디스패치 |
| **P1-2: Error Category** | 2026-02-12 | ErrorInfo, is_retryable, 재시도 정책 |
| **P1-3: 테스트 커버리지** | 2026-02-12 | 297개 테스트, property-based tests |

### ✅ P2 - Performance (성능 최적화)

| 항목 | 완료일 | 주요 내용 |
|------|--------|----------|
| **P2-1: 매트릭 스위칭** | 2026-02-12 | Weighted routing, provider weight 설정 |
| **P2-2: Telemetry** | 2026-02-12 | health_check, TaskTracker, last_errors |
| **P2-3: 배치 최적화** | 2026-02-13 | Priority queue, rate limiter, progress streaming |

### ✅ P3 - Extensibility (확장성)

| 항목 | 완료일 | 주요 내용 |
|------|--------|----------|
| **P3-1: 플러그인 아키텍처** | 2026-02-14 | ProviderPlugin, @register_provider, PluginLoader, entry points |
| **P3-2: 분산 캐싱** | 2026-02-14 | DiskCache, RedisCache, CacheFactory |
| **P3-3: 스트리밍** | 2026-02-14 | StreamProgress, run_with_streaming, MCP progress |

---

## 2. 현재 프로젝트 상태

### 2.1 통계

| 항목 | 수치 |
|------|------|
| **버전** | v0.2.0 |
| **테스트** | 297 passed |
| **Pylint** | 10.00/10 |
| **보안 이슈** | 0 (HIGH/MEDIUM) |
| **소스 파일** | 28개 |
| **코드 라인** | ~6,000+ |

### 2.2 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Tools Layer                       │
│  ask, ask_batch, health_check, list_providers, ...      │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                  Core Services Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ PluginLoader │  │ BatchExecutor│  │StreamProgress│   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │FailoverMgr  │  │ProviderReg  │  │  Cache       │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                  Infrastructure Layer                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │SubprocessAdapt│  │SecuritySanit│  │ SessionMem   │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.3 보안

- ✅ Security Sanitizer (프롬프트/경로 필터링)
- ✅ Path Traversal 방지
- ✅ Command Injection 방지 (shell=False)
- ✅ 하드코딩된 시크릿 없음
- ✅ SAST 스캔 통과 (0 HIGH/MEDIUM issues)

---

## 3. 향후 고려사항 (Optional)

### 3.1 기술적 부채

| 항목 | 우선순위 | 설명 |
|------|---------|------|
| main.py 분할 | 낮음 | 1,865라인 → tools/, handlers/ 분리 |
| Global state 제거 | 낮음 | DI 패턴 도입 |
| Conftest 통합 | 낮음 | 테스트 fixture 중복 제거 |

### 3.2 잠재적 개선

| 항목 | 설명 |
|------|------|
| WebSocket 지원 | 실시간 양방향 통신 |
| OpenTelemetry | 분산 트레이싱 |
| Cache Warming | 시작 시 자주 쓰는 프롬프트 프리로드 |
| Plugin CLI | 플러그인 관리 CLI 도구 |

---

## 4. 버전 히스토리

| 버전 | 날짜 | 내용 |
|------|------|------|
| v0.2.0 | 2026-02-15 | P1~P3 전체 완료, 297 테스트, 보안/품질 검증 |
| v0.1.5 | 2026-02-12 | Phase 3 UX/efficiency, runtime defaults |
| v0.1.4 | 2026-02-11 | Ollama concurrency guard |
| v0.1.3 | 2026-02-10 | Phase 2 hardening |
| v0.1.0 | 2026-02-09 | Initial MCP server |
