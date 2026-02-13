# Model Bridge MCP 개선 로드맵

> 생성일: 2026-02-12
> 상태: 진행중

---

## 1. 현재 상태 분석

### 1.1 프로젝트 개요
- **버전**: v0.1.5 (2026-02-12)
- **Phase**: Phase 1~3 완료
- **테스트**: 124 passed
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

### 1.3 기술적 부채
| 항목 | 심각도 | 추천 액션 |
|------|----------|-------------|
| `main.py` 1388라인 | 중간 | 파일 분할 (`tools/`, `handlers/`) |
| Global state (`CONFIG`, `ADAPTER`...) | 중간 | Dependency Injection 패턴 도입 |
| 중복된 option 처리 로직 | 낮음 | `AskOptions` dataclass로 통합 |
| 하드코딩된 provider dispatchers | 중간 | Registry 기반 라우팅으로 전환 |
| Test fixture 중복 | 낮음 | `conftest.py`로 공통 fixtures 이전 |

---

## 2. 개선 방안

### 🔴 우선순위 1 (즉시 실행 권장)

#### P1-1. Provider Registry 확장 완성
**현재 문제**: `provider_registry.py`가 있으나 실제 라우팅 로직은 `_get_provider_dispatchers()` 하드코딩

**목표**:
- Registry 기반 동적 디스패치로 전환
- Provider capability 협상 구현 (`supports_stream`, `supports_json` 검증)
- 신규 공급자 추가 시 main.py 수정 불필요하게

**파일**:
- `src/model_bridge/core/provider_registry.py` (확장)
- `src/model_bridge/main.py` (리팩토링)

**검증**:
- 신규 provider 추가 시 main.py 수정 불필요
- Capability 기반 tool 필터링 동작

#### P1-2. 에러 카테고리화 및 재시도 정책 개선
**현재 문제**: 모든 에러가 동일하게 "all failed"로 처리

**목표**:
```python
class ErrorCategory(Enum):
    RATE_LIMITED = "rate_limited"      # 재시도 가능
    AUTH_FAILED = "auth_failed"        # 재시도 무의미
    TIMEOUT = "timeout"                 # 재시도 가능
    INVALID_REQUEST = "invalid_request"  # 재시도 무의미
    PROVIDER_UNAVAILABLE = "provider_unavailable"  # 재시도 가능
```

**파일**:
- `src/model_bridge/core/failover_manager.py` (수정)
- `tests/unit/test_failover_retry_policy.py` (신규)

#### P1-3. 유닛한 테스트 커버리지 강화
**현재 상태**: 124 passed이나 edge case 커버리지 부족

**목표**:
1. Property-based 테스트 (Hypothesis 라이브러리)
2. Contract 테스트 (JSON schema 기반 응답 검증)
3. Integration 테스트 (실제 CLI 호출 후 응답 검증)

**파일**:
- `tests/unit/test_property_*.py` (신규)
- `tests/integration/test_cli_contract.py` (신규)
- `pyproject.toml` (의존성 추가)

---

### 🟡 우선순위 2 (중기)

#### P2-1. 매트릭 스위칭 지원
**현재 문제**: config의 `apply_system_suffix`가 provider별 boolean

**목표**:
```yaml
routing:
  default_chains:
    ask_chatgpt_cli:
      - provider: "codex"
        weight: 100
      - provider: "gemini"
        weight: 50
      - provider: "ollama"
        weight: 10
```

#### P2-2. 진정한 Telemetry 및 Observability
**현재 상태**: stderr 로그만 존재

**목표**:
1. 구조화된 로그 (OpenTelemetry 또는 JSON)
2. 메트릭 수집 (요청 지연시간, 성공률, 모델별 사용량)
3. Health Check (`/health` 엔드포인트)

#### P2-3. 배치 실행 성능 최적화
**현재 문제**: `ask_batch`가 Ollama concurrency만 제한

**목표**:
1. Token-bucket rate limiting
2. Priority queue (급紧急 요청 우선 처리)
3. Result streaming (완료된 작업부터 반환)

---

### 🟢 우선순위 3 (장기)

#### P3-1. 플러긴 아키텍처 도입
**목표**: 외부 provider adapter를 플러긴으로 동적 로딩

```python
# plugins/my_provider.py
@register_provider("my_provider")
class MyProviderAdapter(BaseProvider):
    ...
```

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

## 3. 실행 타임라인

```
Week 1-2: P1 항목 구현
├── P1-1: Provider Registry 확장 완성
├── P1-2: Error Category 재시도 정책
└── P1-3: 유닛한 테스트 커버리지 강화

Week 3-4: P2 항목 구현
├── P2-1: 매트릭 스위칭 지원
├── P2-2: Telemetry/Observability 강화
└── P2-3: 배치 실행 성능 최적화

Week 5+: P3 항목 구현
├── P3-1: 플러긴 아키텍처 도입
├── P3-2: 분산 캐싱
└── P3-3: 멀티모달 스트리밍
```

---

## 4. 진행 상태

| 항목 | 상태 | 완료일 | 참고 |
|------|------|----------|------|
| 개선 로드맵 작성 | ✅ 완료 | 2026-02-12 | |
| P1-1: Provider Registry 확장 | ✅ 완료 | 2026-02-12 | `ae06e78` |
| P1-2: Error Category 재시도 정책 | ✅ 완료 | 2026-02-12 | `1fc47c0` |
| P1-3: 테스트 커버리지 강화 | ⏳ 대기중 | | |
| P2-1: 매트릭 스위칭 | ⏳ 대기중 | | |
| P2-2: Telemetry/Observability | ⏳ 대기중 | | |
| P2-3: 배치 성능 최적화 | ⏳ 대기중 | | |

**참고**:
- P1-2: Error category enum 및 ErrorInfo dataclass 추가됨
- retry 결정 로직(_should_continue_failover) 구현됨
- 테스트 작성: regex 패턴이 다소 복잡하여 추후 개선 필요
- 현재 상태: failover_manager.py가 _should_continue_failover 메서드만 추가하고
  실제 failover 로직은 여전히 기존 방식 사용 중
- 향후 개선: execute_async에서 ErrorInfo.from_message() 호출하여
  카테고리 기반 재시도 결정하도록 리팩토링 필요 |

---

## 5. 종합 평가

| 측정 | 평가 |
|------|------|
| **아키텍처** | 우수 - 모듈형 구조 잘 설계됨 |
| **코드 품질** | 양호 - 타입 검증, async 구현 완비 |
| **테스트** | 중간 - 기본 커버리지 있으나 edge case 부족 |
| **문서화** | 우수 - README, Plan, Release Notes 철저 |
| **확장성** | 개선 필요 - 하드코딩된 dispatcher 제거 |

**종합 결론**: 프로젝트가 Phase 1~3을 성공적으로 완료하였으므로, 현재는 **안정화 및 확장성 강화** 단계입니다. Provider Registry 설계문서(`docs/plans/2026-02-11-provider-registry-design.md`)가 이미 작성되어 있으니 이를 구현하는 것이 다음 단계로 가장 적절합니다.
