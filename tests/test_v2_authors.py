"""What each provider says about who wrote a paper, and what we keep of it."""

from __future__ import annotations

from curious_now_v2.pipeline.hydrate import (
    parse_arxiv_authors,
    parse_arxiv_response,
    parse_crossref_authors,
)

ARXIV_ENTRY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2312.07533v2</id>
    <summary>A long enough summary to survive the abstract floor, which exists
    so that a bare label is not mistaken for an abstract worth generating
    from. This sentence is padding for that threshold.</summary>
    <author><name>Ji Lin</name></author>
    <author>
      <name>Hongxu Yin</name>
      <arxiv:affiliation>NVIDIA</arxiv:affiliation>
    </author>
    <author><name>  Li   Fei-Fei  </name></author>
  </entry>
</feed>
"""


def test_arxiv_authors_keep_order_and_the_provider_s_own_spelling() -> None:
    authors = parse_arxiv_authors(ARXIV_ENTRY)["2312.07533"]

    assert [author.full_name for author in authors] == [
        "Ji Lin",
        "Hongxu Yin",
        "Li Fei-Fei",
    ]
    assert [author.position for author in authors] == [0, 1, 2]
    # arXiv publishes one display string, so splitting it would be our guess.
    assert all(author.family is None and author.given is None for author in authors)
    assert authors[1].affiliation == "NVIDIA"
    assert authors[0].affiliation is None


def test_arxiv_authors_key_on_the_bare_id_that_items_store() -> None:
    """The feed echoes v2; an item carries the unversioned identifier."""

    authors = parse_arxiv_authors(ARXIV_ENTRY)

    assert set(authors) == {"2312.07533"}
    # And the abstract parser agrees, so one response joins on one key.
    assert set(parse_arxiv_response(ARXIV_ENTRY)) == set(authors)


def test_arxiv_authors_survive_an_abstract_the_hydrator_would_reject() -> None:
    """The summary gate is about generation; a name is still a name."""

    payload = ARXIV_ENTRY.replace(
        ARXIV_ENTRY[ARXIV_ENTRY.index("<summary>") : ARXIV_ENTRY.index("</summary>")],
        "<summary>Abstract",
    )

    assert parse_arxiv_response(payload) == {}
    assert len(parse_arxiv_authors(payload)["2312.07533"]) == 3


def test_arxiv_authors_of_unparseable_markup_are_empty_not_an_error() -> None:
    assert parse_arxiv_authors("<feed><entry>") == {}


def test_crossref_authors_split_the_name_and_keep_the_orcid() -> None:
    authors = parse_crossref_authors(
        {
            "message": {
                "author": [
                    {
                        "ORCID": "https://orcid.org/0000-0002-5213-0224",
                        "given": "Agrim",
                        "family": "Gupta",
                        "affiliation": [],
                    },
                    {
                        "given": "Li",
                        "family": "Fei-Fei",
                        "affiliation": [{"name": "Stanford University"}],
                    },
                ]
            }
        }
    )

    assert [author.full_name for author in authors] == ["Agrim Gupta", "Li Fei-Fei"]
    assert authors[0].family == "Gupta"
    assert authors[0].given == "Agrim"
    # Stored bare, so the http:// form Crossref also returns compares equal.
    assert authors[0].orcid == "0000-0002-5213-0224"
    assert authors[1].orcid is None
    assert authors[1].affiliation == "Stanford University"
    assert authors[0].affiliation is None


def test_crossref_orcid_is_read_from_either_url_form() -> None:
    def orcid(value: str) -> str | None:
        parsed = parse_crossref_authors(
            {"message": {"author": [{"family": "Ganguli", "ORCID": value}]}}
        )
        return parsed[0].orcid

    assert orcid("http://orcid.org/0000-0002-7481-0810") == "0000-0002-7481-0810"
    assert orcid("https://orcid.org/0000-0002-7481-081X") == "0000-0002-7481-081X"
    # Anything that is not an ORCID is dropped rather than stored as one.
    assert orcid("see the acknowledgements") is None


def test_crossref_group_author_keeps_its_single_name() -> None:
    """A consortium has a `name` and neither a given nor a family."""

    authors = parse_crossref_authors(
        {"message": {"author": [{"name": "The LIGO Scientific Collaboration"}]}}
    )

    assert len(authors) == 1
    assert authors[0].full_name == "The LIGO Scientific Collaboration"
    assert authors[0].family is None


def test_crossref_authors_of_a_work_without_any_are_empty() -> None:
    assert parse_crossref_authors({"message": {}}) == ()
    assert parse_crossref_authors({"message": {"author": "Fei-Fei Li"}}) == ()
    assert parse_crossref_authors({}) == ()
