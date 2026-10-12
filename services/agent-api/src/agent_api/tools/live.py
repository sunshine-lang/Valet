"""会访问外部接口的工具。查天气不需要 Key；联网搜索读取环境变量里的 Key。"""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from agent_api.config import get_settings
from agent_api.tools.base import Tool, ToolContext, ToolError

_WEATHER = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


def _weather_text(code: int | None) -> str:
    if code is None:
        return "未知"
    return _WEATHER.get(code, f"天气代码 {code}")


class GetWeather(Tool):
    name = "get_weather"
    description = "查询某个城市的当前天气，以及未来几天的最高温和最低温。"
    probes = "真实接口：Open-Meteo"
    permission = "network"
    timeout_s = 15.0

    class Args(BaseModel):
        city: str = Field(..., min_length=1, max_length=40, description="城市名，例如北京、上海")
        days: int = Field(3, ge=1, le=7, description="预报天数，1 到 7，含今天")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                return await _forecast(client, args)
        except ToolError:
            raise
        except httpx.HTTPError as error:
            raise ToolError(f"天气服务暂时不可用：{error.__class__.__name__}") from error


async def _forecast(client: httpx.AsyncClient, args: GetWeather.Args) -> dict[str, Any]:
    geo = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": args.city, "count": 1, "language": "zh", "format": "json"},
    )
    geo.raise_for_status()
    places = geo.json().get("results") or []
    if not places:
        raise ToolError(f"没有找到城市：{args.city}")
    place = places[0]
    forecast = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": args.days,
        },
    )
    forecast.raise_for_status()
    data = forecast.json()
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    days = []
    for index, day in enumerate(daily.get("time") or []):
        days.append(
            {
                "date": day,
                "weather": _weather_text((daily.get("weather_code") or [None])[index]),
                "temp_max_c": (daily.get("temperature_2m_max") or [None])[index],
                "temp_min_c": (daily.get("temperature_2m_min") or [None])[index],
            }
        )
    return {
        "city": place.get("name") or args.city,
        "country": place.get("country"),
        "current": {
            "weather": _weather_text(current.get("weather_code")),
            "temperature_c": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
        },
        "forecast": days,
        "source": "open-meteo.com",
    }


class WebSearch(Tool):
    name = "web_search"
    description = (
        "联网搜索，用来查新闻、最新事实，以及模型自己不确定的信息。"
        "用用户正在使用的语言搜一次，不要再用另一种语言搜一遍。返回标题、链接和摘要。"
    )
    probes = "真实接口：博查或 Tavily"
    permission = "network"
    timeout_s = 20.0

    class Args(BaseModel):
        query: str = Field(
            ..., min_length=1, max_length=200, description="一条搜索词，使用用户正在使用的语言"
        )
        count: int = Field(5, ge=1, le=8, description="返回条数，1 到 8")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        settings = get_settings()
        try:
            if settings.bocha_api_key:
                return await _bocha(args.query, args.count, settings.bocha_api_key)
            if settings.tavily_api_key:
                return await _tavily(args.query, args.count, settings.tavily_api_key)
        except httpx.HTTPError as error:
            raise ToolError(f"搜索服务暂时不可用：{error.__class__.__name__}") from error
        raise ToolError(
            "未配置搜索 API。请在 .env 填写 BOCHA_API_KEY 或 TAVILY_API_KEY 后重启后端。"
        )


async def _bocha(query: str, count: int, api_key: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=18) as client:
        response = await client.post(
            "https://api.bochaai.com/v1/web-search",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"query": query, "summary": True, "count": count},
        )
        response.raise_for_status()
        payload = response.json()
    pages = ((payload.get("data") or {}).get("webPages") or {}).get("value") or []
    return {
        "query": query,
        "provider": "bocha",
        "results": [
            {"title": item.get("name"), "url": item.get("url"), "snippet": item.get("snippet")}
            for item in pages[:count]
        ],
    }


async def _tavily(query: str, count: int, api_key: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=18) as client:
        response = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": count},
        )
        response.raise_for_status()
        payload = response.json()
    return {
        "query": query,
        "provider": "tavily",
        "results": [
            {"title": item.get("title"), "url": item.get("url"), "snippet": item.get("content")}
            for item in (payload.get("results") or [])[:count]
        ],
    }


LIVE_TOOLS: list[Tool] = [GetWeather(), WebSearch()]
