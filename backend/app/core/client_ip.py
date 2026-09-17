"""요청의 실제 클라이언트 IP를 뽑아낸다.

Cloudflare(Worker 프록시, 임베딩/LLM 터널 등)를 이미 쓰고 있어서, 요청이 항상
클라이언트와 직접 연결되어 온다고 가정하면 안 된다 - 프록시를 거치면
`request.client.host`는 프록시 자신의 IP가 되어버린다. 그래서 프록시가 실제
클라이언트 IP를 실어 보내는 표준 헤더를 우선 확인하고, 없으면(로컬 개발처럼
직접 연결인 경우) TCP 연결 자체의 IP로 fallback한다.
"""
from fastapi import Request


def get_client_ip(request: Request) -> str:
    # Cloudflare가 프록시할 때 항상 채워주는, 스푸핑 안 되는 실제 클라이언트 IP.
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    # 일반적인 리버스 프록시 표준 헤더 - 여러 프록시를 거치면 콤마로 여러 개 쌓이는데,
    # 맨 앞이 최초 클라이언트다(그 뒤로는 신뢰 안 함 - 위조 가능하므로 첫 값만 참고용).
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first

    # 프록시 없이 직접 연결된 경우(로컬 개발 등).
    if request.client:
        return request.client.host
    return "unknown"
