from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field


class ImportedEntity(BaseModel):
    canonical: str
    aliases: list[str] = Field(default_factory=list)
    source_url: str
    source_license: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    popularity_signal: float | None = None


class DatasetImporter(ABC):
    name: str

    @abstractmethod
    async def import_entities(self, payload: dict[str, Any]) -> list[ImportedEntity]: ...


class RestCountriesImporter(DatasetImporter):
    name = "rest_countries"

    async def import_entities(self, payload: dict[str, Any]) -> list[ImportedEntity]:
        region = str(payload.get("region", "africa")).lower()
        url = f"https://restcountries.com/v3.1/region/{region}?fields=name,population,cca2"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
        rows = response.json()
        max_population = max(int(row.get("population", 0)) for row in rows) or 1
        return [
            ImportedEntity(
                canonical=row["name"]["common"],
                aliases=list(
                    {
                        row["name"].get("official", ""),
                        *row["name"].get("nativeName", {}).keys(),
                        row.get("cca2", ""),
                    }
                    - {""}
                ),
                source_url=url,
                source_license="MPL-2.0 (REST Countries project data aggregation)",
                source_metadata={
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "region": region,
                    "population": row.get("population"),
                },
                popularity_signal=(int(row.get("population", 0)) / max_population) ** 0.35,
            )
            for row in rows
        ]


IMPORTERS: dict[str, DatasetImporter] = {
    RestCountriesImporter.name: RestCountriesImporter(),
}
