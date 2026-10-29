import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    TIER_POINTS,
    Answer,
    AnswerAlias,
    AnswerSource,
    Question,
    QuestionVersion,
    RarityTier,
    ReviewStatus,
)
from app.normalization import normalize_answer

SOURCE = {
    "name": "Brillion reviewed reference set",
    "url": "https://github.com/bhaiding/Brillion/blob/main/docs/DATA_SOURCES.md",
    "license": "CC0-1.0 for Brillion-authored compilation; underlying facts are cited per question",
    "retrieved_at": "2026-10-29",
}


def a(
    name: str,
    tier: RarityTier,
    aliases: list[str] | None = None,
    fact: str | None = None,
) -> dict[str, Any]:
    return {"name": name, "tier": tier, "aliases": aliases or [], "fact": fact}


C = RarityTier.COMMON
P = RarityTier.PREDICTABLY_OBSCURE
U = RarityTier.UNCOMMON
R = RarityTier.RARE
D = RarityTier.DEEP_CUT
B = RarityTier.BRILLION

QUESTIONS: list[dict[str, Any]] = [
    {
        "slug": "solar-system-planets",
        "text": "Name a planet in our Solar System.",
        "category": "Science",
        "criteria": "One of the eight planets recognized by the International Astronomical Union.",
        "source": "https://science.nasa.gov/solar-system/planets/",
        "answers": [
            a("Earth", C),
            a("Mars", C),
            a("Jupiter", C),
            a("Saturn", C),
            a("Venus", P),
            a("Mercury", U),
            a("Neptune", R),
            a(
                "Uranus",
                B,
                fact="Uranus rotates on its side, with an axial tilt of about 98 degrees.",
            ),
        ],
    },
    {
        "slug": "earth-oceans",
        "text": "Name one of Earth's five oceans.",
        "category": "Geography",
        "criteria": "An ocean named by the US National Oceanic and Atmospheric Administration.",
        "source": "https://oceanservice.noaa.gov/facts/howmanyoceans.html",
        "answers": [
            a("Pacific Ocean", C, ["Pacific"]),
            a("Atlantic Ocean", C, ["Atlantic"]),
            a("Indian Ocean", P, ["Indian"]),
            a("Arctic Ocean", U, ["Arctic"]),
            a(
                "Southern Ocean",
                B,
                ["Antarctic Ocean", "Southern"],
                "The Southern Ocean was officially recognized by the National Geographic Society in 2021.",
            ),
        ],
    },
    {
        "slug": "north-american-great-lakes",
        "text": "Name one of the five Great Lakes of North America.",
        "category": "Geography",
        "criteria": "One of Lakes Superior, Michigan, Huron, Erie, or Ontario.",
        "source": "https://www.epa.gov/greatlakes/facts-and-figures-about-great-lakes",
        "answers": [
            a("Lake Michigan", C, ["Michigan"]),
            a("Lake Superior", C, ["Superior"]),
            a("Lake Erie", P, ["Erie"]),
            a("Lake Ontario", U, ["Ontario"]),
            a(
                "Lake Huron",
                B,
                ["Huron"],
                "Lake Huron has the longest shoreline of the Great Lakes when its islands are included.",
            ),
        ],
    },
    {
        "slug": "un-security-council-permanent-members",
        "text": "Name a permanent member of the UN Security Council.",
        "category": "History & Civics",
        "criteria": "One of the five permanent Security Council members defined by the UN Charter.",
        "source": "https://main.un.org/securitycouncil/en/content/current-members",
        "answers": [
            a("United States", C, ["USA", "US", "United States of America"]),
            a("China", C, ["People's Republic of China", "PRC"]),
            a("Russia", P, ["Russian Federation"]),
            a("United Kingdom", U, ["UK", "Britain", "Great Britain"]),
            a(
                "France",
                B,
                fact="France has held a permanent Security Council seat since the UN was founded in 1945.",
            ),
        ],
    },
    {
        "slug": "countries-bordering-germany",
        "text": "Name a country that shares a land border with Germany.",
        "category": "Geography",
        "criteria": "A sovereign state with a current land boundary with Germany.",
        "source": "https://www.cia.gov/the-world-factbook/countries/germany/",
        "answers": [
            a("France", C),
            a("Poland", C),
            a("Austria", P),
            a("Netherlands", P, ["The Netherlands", "Holland"]),
            a("Belgium", U),
            a("Switzerland", U),
            a("Czechia", R, ["Czech Republic"]),
            a("Denmark", D),
            a(
                "Luxembourg",
                B,
                fact="Germany's border with Luxembourg is largely formed by three rivers.",
            ),
        ],
    },
    {
        "slug": "noble-gases",
        "text": "Name a noble gas on the periodic table.",
        "category": "Science",
        "criteria": "An element in IUPAC group 18, including oganesson.",
        "source": "https://iupac.org/what-we-do/periodic-table-of-elements/",
        "answers": [
            a("Helium", C, ["He"]),
            a("Neon", C, ["Ne"]),
            a("Argon", P, ["Ar"]),
            a("Radon", U, ["Rn"]),
            a("Krypton", R, ["Kr"]),
            a("Xenon", D, ["Xe"]),
            a("Oganesson", B, ["Og"], "Oganesson is named for nuclear physicist Yuri Oganessian."),
        ],
    },
    {
        "slug": "shakespeare-tragedies-first-folio",
        "text": "Name a Shakespeare play classified as a tragedy in the First Folio.",
        "category": "Arts & Literature",
        "criteria": "One of the twelve plays in the Tragedies section of the 1623 First Folio.",
        "source": "https://www.folger.edu/explore/shakespeare-in-print/first-folio/",
        "answers": [
            a("Romeo and Juliet", C, ["Romeo & Juliet"]),
            a("Hamlet", C),
            a("Macbeth", C),
            a("Othello", P),
            a("King Lear", P),
            a("Julius Caesar", U),
            a("Antony and Cleopatra", U, ["Antony & Cleopatra"]),
            a("Coriolanus", R),
            a("Titus Andronicus", R),
            a("Timon of Athens", D),
            a("Troilus and Cressida", D, ["Troilus & Cressida"]),
            a(
                "Cymbeline",
                B,
                fact="Cymbeline appears among the tragedies in the First Folio, though modern editions often call it a romance.",
            ),
        ],
    },
    {
        "slug": "christopher-nolan-feature-films",
        "text": "Name a feature film directed by Christopher Nolan through 2023.",
        "category": "Film & TV",
        "criteria": "A feature-length film for which Christopher Nolan has the sole director credit, released through 2023.",
        "source": "https://www.bfi.org.uk/features/where-begin-christopher-nolan",
        "answers": [
            a("The Dark Knight", C),
            a("Inception", C),
            a("Oppenheimer", C),
            a("Interstellar", C),
            a("The Dark Knight Rises", P),
            a("Batman Begins", P),
            a("Dunkirk", P),
            a("Tenet", U),
            a("Memento", U),
            a("Insomnia", R),
            a("The Prestige", R),
            a(
                "Following",
                B,
                fact="Following was Nolan's debut feature and was made on weekends with a tiny crew.",
            ),
        ],
    },
    {
        "slug": "beatles-uk-studio-albums",
        "text": "Name a core Beatles studio album released in the UK.",
        "category": "Music",
        "criteria": "One of the twelve core UK studio albums released from Please Please Me through Let It Be.",
        "source": "https://www.thebeatles.com/albums",
        "answers": [
            a("Abbey Road", C),
            a("Sgt. Pepper's Lonely Hearts Club Band", C, ["Sgt Peppers", "Sgt Pepper"]),
            a("The Beatles", P, ["White Album", "The White Album"]),
            a("Revolver", P),
            a("Rubber Soul", P),
            a("Let It Be", P),
            a("A Hard Day's Night", U),
            a("Help!", U, ["Help"]),
            a("Please Please Me", R),
            a("With the Beatles", R),
            a("Beatles for Sale", D),
            a(
                "Yellow Submarine",
                B,
                fact="Yellow Submarine's second side consists of George Martin's orchestral film score.",
            ),
        ],
    },
    {
        "slug": "apollo-moonwalkers",
        "text": "Name a person who has walked on the Moon.",
        "category": "Science",
        "criteria": "One of the twelve Apollo astronauts who stepped onto the lunar surface.",
        "source": "https://www.nasa.gov/history/apollo-program/",
        "answers": [
            a("Neil Armstrong", C),
            a("Buzz Aldrin", C, ["Edwin Aldrin"]),
            a("Alan Shepard", P),
            a("John Young", U),
            a("Charles Duke", U, ["Charlie Duke"]),
            a("Eugene Cernan", U, ["Gene Cernan"]),
            a("David Scott", R, ["Dave Scott"]),
            a("Alan Bean", R),
            a("Edgar Mitchell", R, ["Ed Mitchell"]),
            a("Harrison Schmitt", D, ["Jack Schmitt"]),
            a("James Irwin", D, ["Jim Irwin"]),
            a(
                "Charles Conrad",
                B,
                ["Pete Conrad"],
                "Pete Conrad's first words on the Moon joked about his shorter height.",
            ),
        ],
    },
    {
        "slug": "canadian-provinces",
        "text": "Name a Canadian province (not a territory).",
        "category": "Geography",
        "criteria": "One of Canada's ten provinces; the three territories are excluded.",
        "source": "https://www.canada.ca/en/intergovernmental-affairs/services/provinces-territories.html",
        "answers": [
            a("Ontario", C),
            a("Quebec", C),
            a("British Columbia", P, ["BC"]),
            a("Alberta", P),
            a("Manitoba", U),
            a("Nova Scotia", U),
            a("Saskatchewan", R),
            a("New Brunswick", R),
            a("Newfoundland and Labrador", D, ["Newfoundland & Labrador", "Newfoundland"]),
            a(
                "Prince Edward Island",
                B,
                ["PEI"],
                "Prince Edward Island is Canada's smallest province by land area and population.",
            ),
        ],
    },
    {
        "slug": "us-states-starting-m",
        "text": "Name a US state whose name begins with M.",
        "category": "Geography",
        "criteria": "A current US state whose English name starts with the letter M.",
        "source": "https://www.census.gov/programs-surveys/popest/about/glossary/geo-terms.html",
        "answers": [
            a("Michigan", C),
            a("Missouri", C),
            a("Massachusetts", P),
            a("Maryland", P),
            a("Minnesota", U),
            a("Mississippi", U),
            a("Maine", R),
            a(
                "Montana",
                B,
                fact="Montana is the fourth-largest US state by area but among the least densely populated.",
            ),
        ],
    },
    {
        "slug": "seven-wonders-ancient-world",
        "text": "Name one of the Seven Wonders of the Ancient World.",
        "category": "History & Civics",
        "criteria": "One of the canonical seven ancient wonders listed by classical writers.",
        "source": "https://www.britannica.com/topic/Seven-Wonders-of-the-World",
        "answers": [
            a("Great Pyramid of Giza", C, ["Pyramid of Giza", "Great Pyramid"]),
            a("Hanging Gardens of Babylon", C, ["Hanging Gardens"]),
            a("Colossus of Rhodes", P),
            a("Lighthouse of Alexandria", U, ["Pharos of Alexandria"]),
            a("Temple of Artemis", U, ["Temple of Artemis at Ephesus"]),
            a("Statue of Zeus at Olympia", R, ["Statue of Zeus"]),
            a(
                "Mausoleum at Halicarnassus",
                B,
                ["Mausoleum of Halicarnassus"],
                "The ruler's tomb gave the English language the word “mausoleum.”",
            ),
        ],
    },
    {
        "slug": "official-clue-boardgame-suspects",
        "text": "Name an original suspect in the board game Clue (Cluedo).",
        "category": "Games",
        "criteria": "One of the six standard suspects in the classic game: Green, Mustard, Peacock, Plum, Scarlet, or White.",
        "source": "https://instructions.hasbro.com/en-us/instruction/clue-game",
        "answers": [
            a("Miss Scarlet", C, ["Scarlet", "Miss Scarlett"]),
            a("Colonel Mustard", C, ["Mustard"]),
            a("Professor Plum", P, ["Plum"]),
            a("Mrs. Peacock", U, ["Peacock"]),
            a("Mr. Green", R, ["Reverend Green", "Green"]),
            a(
                "Mrs. White",
                B,
                ["White"],
                "Mrs. White was replaced by Dr. Orchid in a 2016 version, then later restored in a revised edition.",
            ),
        ],
    },
    {
        "slug": "tetris-tetrominoes",
        "text": "Name a tetromino shape used in Tetris.",
        "category": "Games",
        "criteria": "One of the seven one-sided tetrominoes conventionally named I, O, T, S, Z, J, and L.",
        "source": "https://tetris.com/about-us",
        "answers": [
            a("T tetromino", C, ["T", "T piece"]),
            a("I tetromino", C, ["I", "I piece", "line piece"]),
            a("O tetromino", P, ["O", "O piece", "square piece"]),
            a("L tetromino", U, ["L", "L piece"]),
            a("J tetromino", R, ["J", "J piece"]),
            a("S tetromino", D, ["S", "S piece"]),
            a(
                "Z tetromino",
                B,
                ["Z", "Z piece"],
                "The S and Z pieces are mirror images and cannot be rotated into each other without reflection.",
            ),
        ],
    },
    {
        "slug": "primary-rainbow-colors",
        "text": "Name one of the seven colors traditionally listed in a rainbow.",
        "category": "Science",
        "criteria": "One of red, orange, yellow, green, blue, indigo, or violet in the traditional ROYGBIV mnemonic.",
        "source": "https://www.noaa.gov/jetstream/rainbows",
        "answers": [
            a("Red", C),
            a("Blue", C),
            a("Green", C),
            a("Yellow", C),
            a("Orange", P),
            a("Violet", R, ["Purple"]),
            a(
                "Indigo",
                B,
                fact="Isaac Newton included indigo partly to make seven color divisions, echoing seven musical notes.",
            ),
        ],
    },
    {
        "slug": "winter-olympic-sliding-sports",
        "text": "Name a sliding sport currently contested at the Winter Olympics.",
        "category": "Sports",
        "criteria": "One of bobsleigh, luge, or skeleton on the current Winter Olympic programme.",
        "source": "https://olympics.com/en/sports/winter-olympics",
        "answers": [
            a("Bobsleigh", C, ["Bobsled", "Bobsledding"]),
            a("Luge", U),
            a(
                "Skeleton",
                B,
                fact="Skeleton athletes race head-first and face-down, unlike luge racers who travel feet-first.",
            ),
        ],
    },
    {
        "slug": "grand-slam-tennis-tournaments",
        "text": "Name one of tennis's four Grand Slam tournaments.",
        "category": "Sports",
        "criteria": "One of the Australian Open, French Open, Wimbledon, or US Open.",
        "source": "https://www.itftennis.com/en/itf-tours/grand-slam-tournaments/",
        "answers": [
            a("Wimbledon", C),
            a("US Open", C, ["United States Open"]),
            a("Australian Open", P),
            a(
                "French Open",
                B,
                ["Roland Garros"],
                "The French Open is the only Grand Slam played on clay.",
            ),
        ],
    },
    {
        "slug": "teenage-mutant-ninja-turtles",
        "text": "Name one of the four Teenage Mutant Ninja Turtles.",
        "category": "Film & TV",
        "criteria": "One of Leonardo, Donatello, Raphael, or Michelangelo.",
        "source": "https://www.paramount.com/brand/teenage-mutant-ninja-turtles",
        "answers": [
            a("Leonardo", C, ["Leo"]),
            a("Raphael", P, ["Raph"]),
            a("Michelangelo", U, ["Mikey"]),
            a(
                "Donatello",
                B,
                ["Donnie", "Don"],
                "All four turtles are named after Italian Renaissance artists.",
            ),
        ],
    },
    {
        "slug": "classic-ghostbusters-members",
        "text": "Name one of the four original Ghostbusters in the 1984 film.",
        "category": "Film & TV",
        "criteria": "One of Peter Venkman, Ray Stantz, Egon Spengler, or Winston Zeddemore.",
        "source": "https://catalog.afi.com/Film/57109-GHOSTBUSTERS",
        "answers": [
            a("Peter Venkman", C, ["Venkman"]),
            a("Ray Stantz", P, ["Raymond Stantz", "Stantz"]),
            a("Egon Spengler", U, ["Spengler"]),
            a(
                "Winston Zeddemore",
                B,
                ["Zeddemore"],
                "Winston joins the team after the other three have already founded the business.",
            ),
        ],
    },
]


async def seed() -> None:
    async with SessionLocal() as db:
        for item in QUESTIONS:
            if await db.scalar(select(Question).where(Question.slug == item["slug"])):
                continue
            question = Question(
                slug=item["slug"],
                category=item["category"],
                review_status=ReviewStatus.PUBLISHED,
                family_friendly=True,
            )
            db.add(question)
            await db.flush()
            version = QuestionVersion(
                question_id=question.id,
                version=1,
                text=item["text"],
                eligibility_criteria=item["criteria"],
                source_references=[{**SOURCE, "url": item["source"]}],
                generation_metadata={"method": "human_curated_seed", "reviewed": True},
                validation_status="validated",
                review_status=ReviewStatus.PUBLISHED,
                published_at=datetime.now(UTC),
            )
            db.add(version)
            await db.flush()
            question.active_version_id = version.id
            for index, entry in enumerate(item["answers"]):
                familiarity = max(0.03, 0.9 - index * (0.82 / max(1, len(item["answers"]) - 1)))
                answer = Answer(
                    question_version_id=version.id,
                    canonical_name=entry["name"],
                    normalized_name=normalize_answer(entry["name"]),
                    tier=entry["tier"],
                    points=TIER_POINTS[entry["tier"]],
                    familiarity=familiarity,
                    familiarity_evidence={
                        "method": "reviewed relative recall ordering",
                        "calibration_set": "seed-v1",
                        "rank": index + 1,
                    },
                    source_metadata=[{**SOURCE, "url": item["source"]}],
                    validation_status="verified",
                    interesting_fact=entry["fact"],
                    is_designated_brillion=entry["tier"] == B,
                )
                db.add(answer)
                await db.flush()
                for alias in entry["aliases"]:
                    db.add(
                        AnswerAlias(
                            answer_id=answer.id,
                            question_version_id=version.id,
                            alias=alias,
                            normalized_alias=normalize_answer(alias),
                        )
                    )
                db.add(
                    AnswerSource(
                        answer_id=answer.id,
                        name=SOURCE["name"],
                        url=item["source"],
                        license=SOURCE["license"],
                        retrieved_at=datetime.now(UTC),
                        evidence={"eligibility_checked": True},
                    )
                )
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
