"""Load drafted agronomic guidance into the knowledge base at content_status='DRAFT'.

    python -m scripts.load_knowledge_drafts
    python -m scripts.load_knowledge_drafts --force   # also overwrite existing DRAFT rows

WHAT THIS IS
    Content written from the published sources listed in SOURCES below, summarised
    for this system and cited per condition. It replaces the PLACEHOLDER rows that
    scripts/seed_knowledge.py installs so the recommendation pipeline has something
    real to work with.

WHAT THIS IS NOT
    Reviewed agronomy. Every row lands as DRAFT. A farmer must not act on a DRAFT
    row, and the approval gate in app/api/recommendations.py is what stops that.
    A municipal agricultural technician, a PhilRice/DA officer or your research
    adviser has to read each entry against local practice, correct it, and only
    then set content_status='REVIEWED'.

    Rice varieties, fertiliser rates and pesticide choices are local decisions.
    Where a source gave no Philippine-specific figure, the field says so instead of
    guessing. Those gaps are marked NEEDS LOCAL INPUT and are for your technician to
    fill, not for anyone to leave as they are.

SAFETY
    Never overwrites a row whose content_status is 'REVIEWED'. Without --force it
    also leaves existing DRAFT rows alone, so edits your team has made are safe.
    Re-running is harmless.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import get_config  # noqa: E402
from app.extensions import SessionLocal, init_engine  # noqa: E402
from app.models import Condition, KnowledgeBase, KnowledgeSource  # noqa: E402

GAP = "NEEDS LOCAL INPUT — no Philippine field guidance found in the cited sources."

# --- sources ------------------------------------------------------------------
# year is left None where the document does not state one; inventing a date would
# make the citation worse, not better.
SOURCES = {
    "philrice_field_guide": dict(
        title=("Field Guide: Major Disorders of the Rice Plant — "
               "Diseases and Nutritional Deficiencies"),
        publisher="Philippine Rice Research Institute (PhilRice)",
        year=None,
        url=("https://www.philrice.gov.ph/wp-content/uploads/2023/02/"
             "Field-Guide_-Major-Disorders-of-the-rice-plant-Diseases-and-"
             "Nutritional-Deficiencies.pdf"),
        locator="Accessed 21 November 2026",
    ),
    "philrice_rainy_season": dict(
        title="Preventing rice pests, diseases this rainy season",
        publisher="Philippine Rice Research Institute (PhilRice)",
        year=None,
        url="https://www.philrice.gov.ph/preventing-rice-pests-diseases-rainy-season/",
        locator="Accessed 21 November 2026",
    ),
    "pacific_pests_bph": dict(
        title="Brown planthopper (064)",
        publisher="Pacific Pests, Pathogens and Weeds (Lucidcentral)",
        year=None,
        url=("https://apps.lucidcentral.org/pppw_v12/text/web_full/entities/"
             "rice_brown_planthopper_064.htm"),
        locator="Fact sheet 064; accessed 21 November 2026",
    ),
    "irri_rice_today_flood": dict(
        title=("Variety-based climate-smart intervention helps smallholder farmers "
               "cope with flood in the lowlands of Odisha"),
        publisher="Rice Today, International Rice Research Institute (IRRI)",
        year=None,
        url=("https://ricetoday.irri.org/variety-based-climate-smart-intervention-"
             "helps-smallholder-farmers-cope-with-flood-in-the-lowlands-of-odisha/"),
        locator="Accessed 21 November 2026. India-based; varieties named there are "
                "not Philippine recommendations.",
    ),
}

# --- drafted content ----------------------------------------------------------
DRAFTS: dict[str, dict] = {
    "healthy": {
        "source": None,
        "identification_cues":
            "No damage symptoms. Canopy colour is even and appropriate to the variety "
            "and growth stage, leaves are unmarked, and tillering looks uniform across "
            "the patch. Judge against healthy plants of the same variety and the same "
            "age, not against another field.",
        "cultural_measures":
            "No intervention. Continue the current water and nutrient practice.",
        "preventive_measures":
            "Keep up routine scouting. A healthy reading is a snapshot of one flight "
            "over one patch, not a clearance for the whole field.",
        "monitoring_guidance":
            "Re-scan on the normal schedule. Pay closer attention after heavy rain or "
            "strong wind, and around the booting-to-heading period when several of the "
            "serious conditions establish.",
        "when_to_call":
            "No need to call anyone for this result.",
    },

    "bacterial_leaf_blight": {
        "source": "philrice_field_guide",
        "identification_cues":
            "Two forms. In seedbeds and newly transplanted seedlings (kresek): tiny "
            "water-soaked spots on the lower leaves that enlarge, turn yellow, dry "
            "quickly, and the seedling wilts. From the reproductive stage to maturity: "
            "water-soaked stripes spreading across large areas of the leaf blade, "
            "lesions greyish-white with wavy light-brown margins, and opaque dew-like "
            "drops visible on the lesions in the morning.\n\n"
            "Lookalike: bacterial leaf streak shows linear water-soaked yellowish "
            "streaks running between the veins, not broad uneven grey-brown areas.",
        "cultural_measures":
            "Reduce plant injury during transplanting — the bacteria enter through "
            "wounds and natural openings. Destroy plant residues; the pathogen survives "
            "on stubble, rice straw, weeds and infected seed. Prepare land well before "
            "planting so undecomposed stubble and straw are not carried over.",
        "preventive_measures":
            "Plant a resistant variety; PhilRice names PSB Rc242 as resistant to "
            "bacterial leaf blight. Use seed from healthy plants, or treated seed. "
            "Avoid excessive nitrogen, and avoid magnesium silicate fertilisation. "
            "Correct phosphorus or potassium deficiency, which predisposes the crop.",
        "monitoring_guidance":
            "The disease is favoured by 25–35°C, strong wind and heavy rain, so scout "
            "after storms and through the wet season. Check nitrogen practice and P/K "
            "status at the same time; both change how fast it spreads.",
        "when_to_call":
            "Call your municipal agricultural technician before applying anything. "
            "PhilRice states plainly that chemical control of bacterial leaf blight is "
            "neither economical nor effective, so spraying is usually money lost as "
            "well as an unnecessary input.",
    },

    "rice_blast": {
        "source": "philrice_field_guide",
        "identification_cues":
            "Leaf blast: small to spindle-shaped spots with a brown border and a grey "
            "centre, which join up until leaves dry and die. Most susceptible from "
            "seedling to tillering. Node blast: a blackened, rotten node that later "
            "breaks, around tillering. Panicle (neck) blast: a blackened panicle base "
            "that later breaks, with unfilled grains, from booting to heading.\n\n"
            "Lookalikes: brown spot lesions are circular to oval, not spindle-shaped; "
            "sheath blight makes large irregular lesions.",
        "cultural_measures":
            "Raise seedlings on a wet bed. Avoid water stress — the disease is worse "
            "where water is short and night humidity high. Destroy infected crop "
            "residues.",
        "preventive_measures":
            "Plant a resistant variety; this is the measure PhilRice recommends most "
            "strongly, and it names PSB Rc10 as resistant to blast. Avoid high nitrogen "
            "fertilisation.",
        "monitoring_guidance":
            "Favoured by overcast skies, light rain, long dew periods and low night "
            "temperature. Spores are released at night in dew or rain, germinate within "
            "about 4 hours, invade in 8–10 hours, and lesions show after about 4 days — "
            "so scout 4 to 5 days after a run of wet overcast nights. One large lesion "
            "on a susceptible variety can release 2,000–6,000 spores a night for around "
            "two weeks, and wind carries them a long way, so a small patch is worth "
            "reporting early.",
        "when_to_call":
            "Call your municipal agricultural technician before applying any fungicide, "
            "and immediately if you find blackened nodes or panicle bases during "
            "booting or heading, when yield loss is heaviest.",
    },

    "brown_spot": {
        "source": "philrice_field_guide",
        "identification_cues":
            "Small circular to oval spots with grey centres, scattered over the leaf, "
            "from tillering onward; spots fuse and the leaf withers. At maturity, black "
            "spots on the glumes covered by a dark brown velvety spore mat, with "
            "discoloured shrivelled seed. In seedlings, brown spots on the coleoptile "
            "and black lesions on roots. Most common in shaded parts of the field and "
            "where soil is potash-deficient or saline.\n\n"
            "Lookalikes: blast lesions are spindle-shaped. Potassium deficiency also "
            "browns older leaves, but with yellowing between the veins.",
        "cultural_measures":
            "Apply balanced fertilisation and manage water well. Practise field "
            "sanitation and use soil amendments. Destroy stubble and weeds that carry "
            "inoculum. Where potassium is deficient, muriate of potash is the correction "
            "PhilRice names — confirm the deficiency first rather than applying blind.",
        "preventive_measures":
            "Plant certified seed. The fungus is seedborne, infected seed germinates "
            "poorly, and infection then starts in the seedbed.",
        "monitoring_guidance":
            "Favoured by cloudy weather, light rain, heavy dew and 20–29°C. Treat a "
            "brown spot finding as a prompt to check the field's potassium status and "
            "for salinity, since the disease tends to follow them.",
        "when_to_call":
            "Call your municipal agricultural technician before buying fertiliser to "
            "correct a suspected deficiency, and ask about a soil test rather than "
            "treating on symptoms alone.",
    },

    "hopperburn": {
        "source": "pacific_pests_bph",
        "identification_cues":
            "Plants at the milk or dough stage yellow from the leaf tip, then brown, dry "
            "out and collapse, usually in patches rather than evenly. Confirm it is "
            "insects and not a disease by parting the canopy and looking at the base of "
            "the plants, where it is shady and humid: nymphs and winged and wingless "
            "adults will be there. Sooty mould blackening the stems usually means large "
            "numbers. Hopperburn is more common in paddy than in dryland rice.",
        "cultural_measures":
            "Drain the paddy for 3–4 days early in an infestation. Split nitrogen into "
            "three applications rather than fewer, larger ones. Let weeds on the bunds "
            "and field borders flower, which feeds the natural enemies. Do not ratoon "
            "the crop, and plough the field after harvest so stubble cannot carry "
            "breeding over.",
        "preventive_measures":
            "Choose a tolerant variety, accepting that planthoppers sometimes overcome "
            "resistance. Plant within 2–3 weeks of your neighbours — staggered planting "
            "across a barangay keeps a continuous food supply available. Remove "
            "volunteer plants, and rotate rice with other crops.",
        "monitoring_guidance":
            "Count insects per tiller at the plant base. More than 3–5 per tiller is "
            "high and calls for closer observation and possibly treatment. Below that, "
            "keep watching rather than spraying.",
        "when_to_call":
            "Call your municipal agricultural technician before any insecticide. "
            "Broad-spectrum sprays kill the spiders, coccinellid beetles, dragonflies, "
            "damselflies and mirid bugs that hold the population down, and numbers then "
            "rebound higher than before spraying — the resurgence effect. Insecticide is "
            "justified only where the population is likely to reach an economic injury "
            "level, and the product and timing must follow current local recommendations.",
    },

    "nitrogen_deficiency": {
        "source": "philrice_field_guide",
        "identification_cues":
            "Stunted plants with fewer tillers. Leaves small, narrow and erect, turning "
            "yellowish then reddish-brown; older leaves go light straw-coloured and "
            "wither. The yellowing is general rather than patterned. Most obvious at the "
            "vegetative stage. Judge against healthy plants of the same variety and age.\n\n"
            "Lookalikes: tungro and grassy stunt also stunt and yellow the crop. Rule "
            "those out before treating this as a fertiliser problem — adding nitrogen to "
            "a virus-infected field wastes the input and raises disease pressure.",
        "cultural_measures":
            "Apply nitrogen as needed using the leaf colour chart rather than a fixed "
            "calendar. Split applications to improve efficiency.",
        "preventive_measures":
            "Have the soil analysed. PhilRice points to routine N-P-K analysis roughly "
            "every 5 years through the Bureau of Soils and Water Management, quoted at "
            "₱130 per sample at 2021 rates. Sampling method: dig about 20 cm deep, take "
            "5 cm thick slices at three random points, keep a middle strip about 10 cm "
            "wide, mix into one composite sample and submit about 1 kg. Intensive "
            "cropping without replacement makes the deficiency worse over time.",
        "monitoring_guidance":
            "Take leaf colour chart readings on the schedule your technician sets. "
            "The cited guide gives no LCC threshold values, so use the local DA "
            "threshold for your variety — " + GAP,
        "when_to_call":
            "Call your municipal agricultural technician before changing the fertiliser "
            "programme. Over-correcting matters: excessive nitrogen is a listed "
            "predisposing factor for both bacterial leaf blight and blast.",
    },

    "lodging": {
        "source": None,
        "identification_cues":
            "Stems bent over or flattened, usually in patches and usually after strong "
            "wind or heavy rain. Record whether panicles are lying in standing water, "
            "because grain in contact with water sprouts and is lost quickly.",
        "cultural_measures": GAP + " Report the affected area and the growth stage to "
            "your technician so the decision on early harvest can be made on the spot.",
        "preventive_measures": GAP + " Avoiding excessive nitrogen and maintaining "
            "potassium are the measures usually given for stem strength, but no "
            "Philippine figure was found in the sources cited here, so treat this as a "
            "prompt for your adviser rather than guidance.",
        "monitoring_guidance":
            "Re-scan after every storm, particularly from booting onwards when the "
            "panicle weight makes the crop most vulnerable.",
        "when_to_call":
            "Call your municipal agricultural technician promptly. Whether to harvest "
            "early depends on growth stage, grain moisture and the weather forecast, and "
            "that judgement has to be made locally.",
    },

    "flooding": {
        "source": "irri_rice_today_flood",
        "identification_cues":
            "Crop partly or completely under water, or — once water has receded — limp "
            "yellowed leaves and a silt coating on the canopy. Record how long the water "
            "has been standing; duration matters more than depth for survival.",
        "cultural_measures":
            "Drain the field as soon as there is anywhere for the water to go. Once the "
            "water recedes, assess how much of the crop is actually alive before "
            "deciding between letting it recover, replanting, or sowing a short-duration "
            "crop in the remaining window. Replanting is often limited by whether "
            "seedlings of the right age can be obtained at all.",
        "preventive_measures":
            "Submergence-tolerant (Sub1) varieties exist and can offset much of the "
            "damage from inundation. The cited article is from Odisha, India, and the "
            "varieties it names are not Philippine recommendations — ask your DA office "
            "which submergence-tolerant variety is recommended for South Cotabato. "
            + GAP,
        "monitoring_guidance":
            "Stagnant water is the limit, not the flooding itself: even flood-tolerant "
            "varieties may fail where water remains more than about 15 days, and no "
            "known variety tolerates both flash flooding and stagnant flooding. Record "
            "the date the water arrived, so the 15-day mark is a known date and not a "
            "guess.",
        "when_to_call":
            "Call your municipal agricultural technician while the field is still under "
            "water if you can. The replant-or-recover decision is time-critical and gets "
            "harder the longer it is left.",
    },

    "unknown": {
        "source": None,
        "identification_cues":
            "This is not a diagnosis. It means the model was not confident enough to "
            "name a condition, or what is in the photo is not one of the conditions the "
            "system is trained on.",
        "cultural_measures":
            "Do not treat anything on the strength of this result. Applying a pesticide "
            "or fertiliser against an unidentified problem is how the wrong input gets "
            "used and the real cause gets missed.",
        "preventive_measures":
            "Take close-up photographs of the affected plants — whole plant, the leaf "
            "or panicle in question, and the base of the plant — and note the growth "
            "stage, how much of the field is affected, and what the weather has been "
            "doing. Those are what a technician needs in order to identify it.",
        "monitoring_guidance":
            "Flag the area and re-scan it on the next flight. Something unidentifiable "
            "today is often obvious a week later.",
        "when_to_call":
            "Call your municipal agricultural technician. Every unknown result should "
            "reach a person; that is the point of the verification queue.",
    },
}


def upsert_sources(session) -> dict[str, int]:
    ids = {}
    for key, data in SOURCES.items():
        existing = session.execute(
            select(KnowledgeSource).where(
                KnowledgeSource.title == data["title"],
                KnowledgeSource.publisher == data["publisher"],
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = KnowledgeSource(**data)
            session.add(existing)
            session.flush()
        ids[key] = existing.id
    session.commit()
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="also overwrite rows already at DRAFT (never touches REVIEWED)")
    args = parser.parse_args()

    cfg = get_config()
    init_engine(cfg.sqlalchemy_uri)
    session = SessionLocal()

    source_ids = upsert_sources(session)

    written = skipped_reviewed = skipped_draft = missing = 0
    for code, draft in DRAFTS.items():
        cond = session.execute(
            select(Condition).where(Condition.code == code)
        ).scalar_one_or_none()
        if cond is None:
            print(f"  no such condition, skipped: {code}")
            missing += 1
            continue

        row = session.execute(
            select(KnowledgeBase).where(KnowledgeBase.condition_id == cond.id)
        ).scalar_one_or_none()

        if row is not None and row.content_status == "REVIEWED":
            print(f"  REVIEWED, left alone: {code}")
            skipped_reviewed += 1
            continue
        if row is not None and row.content_status == "DRAFT" and not args.force:
            print(f"  already DRAFT, left alone (use --force): {code}")
            skipped_draft += 1
            continue

        source_id = source_ids.get(draft["source"]) if draft["source"] else None
        fields = dict(
            identification_cues=draft["identification_cues"],
            cultural_measures=draft["cultural_measures"],
            preventive_measures=draft["preventive_measures"],
            monitoring_guidance=draft["monitoring_guidance"],
            when_to_call=draft["when_to_call"],
            source_id=source_id,
            content_status="DRAFT",
        )
        if row is None:
            session.add(KnowledgeBase(condition_id=cond.id, **fields))
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        print(f"  written as DRAFT: {code}")
        written += 1

    session.commit()
    SessionLocal.remove()

    print()
    print(f"DRAFT rows written:   {written}")
    print(f"left alone (REVIEWED): {skipped_reviewed}")
    print(f"left alone (DRAFT):    {skipped_draft}")
    print(f"condition not found:   {missing}")
    print()
    print("These rows are DRAFT. They are summarised from published sources, not")
    print("reviewed agronomy, and no farmer should act on them yet. A technician or")
    print("adviser must check each entry against local practice, fill in every field")
    print("marked NEEDS LOCAL INPUT, and only then set content_status='REVIEWED'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
