-- 레포(Nexus)에 있는 확장의 현황을 미러링하는 테이블.
-- 업로드/웹스토어 다운로드 출처를 구분하지 않고, id+version 조합마다 한 행을 유지한다.
-- 같은 id라도 version이 다르면 별개 확장으로 취급한다(PRIMARY KEY가 ext_id+version).
CREATE TABLE IF NOT EXISTS extension_registry (
    ext_id TEXT NOT NULL,
    version TEXT NOT NULL,
    ext_name TEXT NOT NULL,
    browser TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'review',
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ext_id, version)
);
