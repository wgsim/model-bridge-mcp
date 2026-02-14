# Model Bridge MCP 개선 로드맵

> 생성일: 2026-02-12
> 상태: 진행중

---

## 1. 현재 상태 분석

### 1.1 프로젝트 개요
- **버전**: v0.1.5 (2026-02-12)
- **Phase**: Phase 1~3 완료
- **테스트**: 137 passed
- **CI/CD**: GitHub Actions + pre-commit 구성됨

### 1.2 아키텍처 강점
```
입력 → Security Sanitizer → Failover Manager → Subprocess Adapter → CLI 도구들
                                  ↓
                        Provider Registry (Capability Tracking)
                                  ↓
                        Cache/Session Memory Layer
```

**설계 우수 사항**:
1. 모듈형 구조 (`core/`, `adapters/`, `security/`, `config/`)
2. Type-safe Config (Pydantic 기반 스키마 검증)
3. Async-first (asyncio 기반 비동기 실행)
4. Security First (프롬프트 sanitizing + 시스템 경로 보안)

---

## 2. 개선 방안

### 🔴 우선순위 1 (즉시 실행 권장)

#### P1-1. Provider Registry 확장 완성
**상태**: ✅ 완료

#### P1-2. 에러 카테고리화 및 재시도 정책 개선
**상태**: ✅ 완료

#### P1-3. 유닛한 테스트 커버리지 강화
**상태**: ✅ 완료

---

### 🟡 우선순위 2 (중기)

#### P2-1. 매트릭 스위칭 지원
**상태**: ✅ 완료

#### P2-2. 진정한 Telemetry 및 Observability
**상태**: ✅ 완료

#### P2-3. 배치 실행 성능 최적화
**상태**: ✅ 완료

---

### 🟢 우선순위 3 (장기)

#### P3-1. 플러긴 아키텍처 도입
**상태**: ⏳ 진행중
**목표**: 외부 provider adapter를 플러긴으로 동적 로딩

```python
# plugins/my_provider.py
@register_provider("my_provider")
class MyProviderAdapter(BaseProvider):
    ...
```

**구현 내용**:
- `ProviderPlugin` 추상 클래스
- `@register_provider` 데코레이터
- `PluginLoader` 클래스 (발견 및 로딩)
- Built-in plugins (codex, gemini, ollama, claude_code)

#### P3-2. 분산 캐싱 (Redis/Disk-backed)
**현재 상태**: In-memory만 존재 (TTL 300s)

**목표**:
1. Redis 기반 분산 캐싱
2. Disk persistence (영속성 보장)
3. Cache warming (자주 사용되는 프롬프트 미리 로딩)

#### P3-3. 멀티모달 스트리밍 지원
**현재 제한**: `stream=True` 시 청크 fallback만 제공

**목표**:
1. MCP SSE (Server-Sent Events) 지원
2. 실시간 진행률 전송
3. 중단 시 재개 지원

---

## 4. 진행 상태

| 항목 | 상태 | 완료일 | 참고 |
|------|------|----------|------|
| 개선 로드맵 작성 | ✅ 완료 | 2026-02-12 | |
| P1-1: Provider Registry 확장 | ✅ 완료 | 2026-02-12 | `ae06e78` |
| P1-2: Error Category 재시도 정책 | ✅ 완료 | 2026-02-12 | `1fc47c0` |
| P1-3: 테스트 커버리지 강화 | ✅ 완료 | 2026-02-12 | `15dda52` |
| P2-1: 매트릭 스위칭 | ✅ 완료 | 2026-02-12 | `121f976`, `ffe79c7` |
| P2-2: Telemetry/Observability | ✅ 완료 | 2026-02-12 | `28a7ec3` |
| P2-3: 배치 성능 최적화 | ✅ 완료 | 2026-02-13 | `1b87617` |
| P3-1: 플러긴 아키텍처 | ⏳ 진행중 | | ProviderPlugin, PluginLoader, @register_provider |
| P3-2: 분산 캐싱 | ⏳ 대기중 | | |
| P3-3: 멀티모달 스트리밍 | ⏳ 대기중 | | |

---

## 5. 종합 평가

| 측정 | 평가 |
|------|------|
| **아키텍처** | 우수 - 모듈형 구조 잘 설계됨 |
| **코드 품질** | 양호 - 타입 검증, async 구현 완비 |
| **테스트** | 중간 - 기본 커버리지 있으나 edge case 부족 |
| **문서화** | 우수 - README, Plan, Release Notes 철저 |
| **확장성** | 개선 필요 - 플러그인 아키텍처로 개선 중 |
