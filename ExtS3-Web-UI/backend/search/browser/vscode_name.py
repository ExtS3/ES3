import requests
import httpx


SEARCH_URL = "https://open-vsx.org/api/-/search"


def vscode_search_by_name(query, size=20):
    try:
        res = requests.get(
            SEARCH_URL,
            params={"query": query, "size": size},
            timeout=10,
        )
        res.raise_for_status()
        payload = res.json()

        ext_ids = []
        for ext in payload.get("extensions") or []:
            namespace = ext.get("namespace")
            name = ext.get("name")
            if namespace and name:
                ext_ids.append(f"{namespace}.{name}")
        return ext_ids
    except Exception as e:
        print(f"VSCode search error: {e}")
        return []


async def vscode_search_by_name_async(query, size=20):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                SEARCH_URL,
                params={"query": query, "size": size},
            )
        res.raise_for_status()
        payload = res.json()

        ext_ids = []
        for ext in payload.get("extensions") or []:
            namespace = ext.get("namespace")
            name = ext.get("name")
            if namespace and name:
                ext_ids.append(f"{namespace}.{name}")
        return ext_ids
    except Exception as e:
        print(f"VSCode search error: {e}")
        return []
