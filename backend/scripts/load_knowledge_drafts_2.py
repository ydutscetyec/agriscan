"""Load drafted agronomic guidance for the 16 modelA_v2 classes that scripts.load_knowledge_drafts leaves at PLACEHOLDER.

    python -m scripts.load_knowledge_drafts_2
    python -m scripts.load_knowledge_drafts_2 --force   # also overwrite existing DRAFT rows
    python -m scripts.load_knowledge_drafts_2 --dry-run # print what would change, touch nothing

WHY THIS FILE EXISTS
    scripts/load_knowledge_drafts.py covers the nine Tier-1 conditions and reaches nine
    of modelA_v2's 25 classes through MODEL_CLASS_DRAFTS. Its own comment records that
    the other sixteen "have no draft at all -- the sources consulted covered the Tier-1
    conditions only", and keeps them at PLACEHOLDER.

    Those sixteen are two thirds of what the deployed classifier can output. Until they
    have content, a correct detection still produces the generic PLACEHOLDER string, so
    the system names the problem and then says nothing useful about it.

    This is a separate module rather than an edit to load_knowledge_drafts.py so the
    reviewed-and-known file is not disturbed, and so a technician can see exactly which
    sixteen entries are new and review them as one batch.

WHAT THIS IS
    Content written from the published sources in SOURCES below, summarised for this
    system and cited per condition. PhilRice is used wherever PhilRice covers the
    condition. Where it does not, the source is named and its origin flagged, because
    varieties, thresholds and inputs from Louisiana, Tamil Nadu or Sri Lanka are not
    Philippine recommendations.

WHAT THIS IS NOT
    Reviewed agronomy. Every row lands as DRAFT. A farmer must not act on a DRAFT row,
    and the approval gate in app/api/recommendations.py is what stops that. A municipal
    agricultural technician, a PhilRice/DA officer or your research adviser has to read
    each entry against local practice, correct it, and only then set REVIEWED.

    No pesticide, fungicide or herbicide product is named anywhere in this file, even
    where a source named one. Several sources name actives that are restricted or
    banned in the Philippines. Product choice is a decision for a technician holding
    the current DA/FPA registered list, not for this database.

SAFETY
    Never overwrites a row whose content_status is 'REVIEWED'. Without --force it also
    leaves existing DRAFT rows alone, so edits your team has made are safe. Re-running
    is harmless. Idempotent, like its sibling.

CLASS-CODE NOTE
    Keys below are the exact modelA_v2 class strings from scripts/conditions_modelA_v2.csv,
    because that is what detections carry. conditions.code is utf8mb4_general_ci, so the
    lookup is case-insensitive; the handled-set guard from the sibling script is kept so a
    future collision is reported rather than hidden behind a uq_kb_condition violation.
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

GAP = "NEEDS LOCAL INPUT -- no Philippine field guidance found in the cited sources."

NON_PH = ("Not a Philippine source. Varieties, thresholds, rates and products named "
          "there must not be carried over; a technician has to supply the local "
          "equivalent.")

SOURCES = {
    "philrice_diseases_ph": dict(
        title="Major diseases of the rice plant in the Philippines",
        publisher="Philippine Rice Research Institute (PhilRice)",
        year=None,
        url=("https://www.philrice.gov.ph/wp-content/uploads/2023/02/"
             "Major-diseases-of-the-rice-plant-in-the-Philippines.pdf"),
        locator="Accessed 21 November 2026",
    ),
    "philrice_harmful_organisms": dict(
        title="Harmful organisms in Philippine rice fields",
        publisher="Philippine Rice Research Institute (PhilRice)",
        year=None,
        url=("https://www.philrice.gov.ph/wp-content/uploads/2023/02/"
             "Harmful-organisms-in-Philippine-rice-fields.pdf"),
        locator="Accessed 21 November 2026",
    ),
    "philrice_field_guide_organisms": dict(
        title=("Field Guide: Harmful and useful organisms in Philippine rice fields "
               "-- Insects and Non-insects (Revised Edition)"),
        publisher="DA-Philippine Rice Research Institute (PhilRice)",
        year=None,
        url=("https://www.philrice.gov.ph/wp-content/uploads/2023/02/"
             "Field-Guide_-Harmful-and-useful-organisms-in-Philippine-rice-fields-"
             "Insects-and-Non-insects.pdf"),
        locator="ISBN 971-9081-03-1; accessed 21 November 2026",
    ),
    "philrice_weeds_lowland": dict(
        title="Weeds in irrigated and rainfed lowland ricefields in the Philippines",
        publisher=("Crop Protection Division, Philippine Rice Research Institute "
                   "(PhilRice), with KOPIA Center Philippines"),
        year=None,
        url="https://www.philrice.gov.ph/weeds-irrigated-rainfed-lowland-ricefields-philippines",
        locator="Donayre, Martin and Santiago; accessed 21 November 2026",
    ),
    "pjs_cyperus_critical_period": dict(
        title="Critical Periods of Controlling Cyperus rotundus L. under Flooded Rice Conditions",
        publisher="Philippine Journal of Science 152(1): 313-324",
        year=2023,
        url="https://doi.org/10.56899/152.01.24",
        locator="Donayre DK et al.; accessed 21 November 2026",
    ),
    "irri_yellowing_syndrome": dict(
        title=("Philippine partners strengthen capacity to detect Rice Yellowing "
               "Syndrome with support from IRRI"),
        publisher="International Rice Research Institute (IRRI)",
        year=2026,
        url=("https://www.irri.org/news-and-events/news/philippine-partners-strengthen-"
             "capacity-detect-rice-yellowing-syndrome-support"),
        locator="31 March 2026; accessed 21 November 2026",
    ),
    "pacific_pests_false_smut": dict(
        title="Rice false smut (428)",
        publisher="Pacific Pests, Pathogens and Weeds (Lucidcentral)",
        year=None,
        url=("https://apps.lucidcentral.org/pppw_v12/text/web_full/entities/"
             "rice_false_smut_428.htm"),
        locator="Fact sheet 428; accessed 21 November 2026",
    ),
    "pacific_pests_stem_rot": dict(
        title="Rice stem rot (430)",
        publisher="Pacific Pests, Pathogens and Weeds (Lucidcentral)",
        year=None,
        url=("https://apps.lucidcentral.org/pppw_v12/text/web_full/entities/"
             "rice_stem_rot_430.htm"),
        locator="Fact sheet 430; accessed 21 November 2026",
    ),
    "uada_cercospora": dict(
        title="Cercospora Diseases in Rice (FSA2213)",
        publisher=("University of Arkansas System Division of Agriculture, "
                   "Cooperative Extension Service"),
        year=None,
        url="https://www.uaex.uada.edu/publications/pdf/FSA2213.pdf",
        locator="Accessed 21 November 2026. " + NON_PH,
    ),
    "doa_lk_sheath_rot": dict(
        title="Rice Diseases: Sheath Rot",
        publisher="Rice Research and Development Institute, Department of Agriculture, Sri Lanka",
        year=None,
        url="https://doa.gov.lk/?p=25414",
        locator="Accessed 21 November 2026. " + NON_PH,
    ),
    "frontiers_sheath_rot_review": dict(
        title="Rice Sheath Rot: An Emerging Ubiquitous Destructive Disease Complex",
        publisher="Frontiers in Plant Science 6:1066",
        year=2015,
        url="https://doi.org/10.3389/fpls.2015.01066",
        locator="Bigirimana VP et al.; accessed 21 November 2026",
    ),
    "tnau_rice_pests": dict(
        title="Crop Protection: Pests of paddy -- Thrips (Stenchaetothrips biformis)",
        publisher="TNAU Agritech Portal, Tamil Nadu Agricultural University",
        year=None,
        url=("https://agritech.tnau.ac.in/crop_protection/rice/"
             "crop_prot_crop_insectpest%20_cereals_paddy_m16.html"),
        locator="Accessed 21 November 2026. " + NON_PH,
    ),
    "tnau_stunt_viruses": dict(
        title="Expert System for Paddy: Grassy stunt virus and Ragged stunt virus",
        publisher="TNAU Agritech Portal, Tamil Nadu Agricultural University",
        year=None,
        url="https://agritech.tnau.ac.in/expert_system/paddy/cpdisstunragg.html",
        locator="Compiled from IRRI material; accessed 21 November 2026. " + NON_PH,
    ),
}


# --- the sixteen classes load_knowledge_drafts.py leaves at PLACEHOLDER ----------
# Keys are modelA_v2 class codes, verbatim from scripts/conditions_modelA_v2.csv.
DRAFTS_2: dict[str, dict] = {

    # ------------------------------------------------------------------ fungal
    "Sheath Blight": {
        "source": "philrice_diseases_ph",
        "identification_cues":
            "Local names: labhagsa pal-ak (Cebuano), masot (Pangasinan).\n\n"
            "On the leaf sheath, greenish-grey oval spots near the water line, which "
            "enlarge and turn greyish-white with a brown margin. The lesions spread to "
            "upper leaf sheaths and to any leaf touching an infected part. On the leaf, "
            "a banded brownish lesion with a grey-white centre; lesions join up and "
            "blight the leaf. If the flag leaf is infected, panicle exsertion is "
            "affected.\n\n"
            "Lookalikes: the position is the tell. Sheath blight starts at the water "
            "line and works upward; blast lesions are spindle-shaped and on the blade; "
            "brown spot lesions are circular to oval and scattered. Several other sheath "
            "diseases (sheath rot, stem rot, sheath spot) also sit low on the plant -- if "
            "the lesion is at the boot enclosing the panicle it is more likely sheath "
            "rot, and if there are hard black bodies in or on the sheath it is more "
            "likely stem rot.",
        "cultural_measures":
            "Dry the field after harvest and monitor fertilisation; PhilRice names the "
            "Leaf Color Chart and the Minus-One Element Technique as the tools for that. "
            "Observe the optimum seeding rate and use wider plant spacing. Drain the "
            "field at maximum tillering for a few days. Ensure proper sanitation: deep "
            "plough to bury infected stubble and weeds, and expose the soil to intense "
            "sunlight.",
        "preventive_measures":
            "Plant a resistant variety where one is available for your area. Keep "
            "nitrogen off the high end: PhilRice lists high rates of nitrogen "
            "fertiliser, and dense or close planting, as factors that favour the "
            "disease, so the seeding rate and the fertiliser programme are the two "
            "levers set before the crop goes in.",
        "monitoring_guidance":
            "Favoured by a susceptible variety, highly humid and warm weather, frequent "
            "rains, high nitrogen and dense planting. PhilRice's instruction is to "
            "assess the field before maximum tillering and before panicle emergence -- "
            "those are the two checkpoints, not a weekly count. A finding here is also "
            "a prompt to look at your seeding rate and nitrogen for the next crop.",
        "when_to_call":
            "Call your municipal agricultural technician if lesions are climbing toward "
            "the flag leaf, or if the field has the combination PhilRice flags (dense "
            "stand plus high nitrogen plus frequent rain) -- that is a field set up to "
            "repeat the problem next season, and the fix is in the plan, not the spray. "
            "Fungicide choice and timing are a technician's call. " + GAP,
    },

    "Sheath Rot": {
        "source": "doa_lk_sheath_rot",
        "identification_cues":
            "Lesions on the uppermost leaf sheath -- the boot leaf enclosing the young "
            "panicle -- at the booting stage. Oblong to irregular oval spots with grey "
            "or light-brown centres and a diffuse dark reddish-brown margin, giving an "
            "irregular target pattern. The spots enlarge and can cover most of the "
            "sheath. In severe infection the panicle does not emerge, or emerges only "
            "partly, then rots; a whitish powdery fungal growth forms inside the "
            "sheath.\n\n"
            "IMPORTANT for this class: 'sheath rot' is a disease complex, not one "
            "pathogen. Sarocladium oryzae, several Fusarium species and the bacterium "
            "Pseudomonas fuscovaginae all produce symptoms the published review "
            "describes as very similar. A photograph cannot separate them, and this "
            "class should not be read as naming S. oryzae specifically.\n\n"
            "Lookalikes: sheath blight starts at the water line and climbs, not at the "
            "boot. The disease is also reported to follow insect injury and virus "
            "infection, so check whether something else damaged the plant first.",
        "cultural_measures":
            "Within the season, the cited guidance is to keep nitrogen at the "
            "recommended dose or apply it on the basis of a leaf colour chart, because "
            "excessive nitrogen is listed among the conditions favouring the disease. "
            "For the following season: improve soil condition with organic fertiliser, "
            "and use certified seed paddy free of the disease.",
        "preventive_measures":
            "Use certified seed. Because the complex includes seedborne agents and the "
            "disease follows wounding, protecting the crop from insect damage through "
            "booting is part of preventing it. " + GAP,
        "monitoring_guidance":
            "Favoured by temperatures of roughly 20-28 C and high humidity during "
            "flowering to grain filling. The window that matters is booting to heading, "
            "when the panicle is still inside the sheath -- open a few boot leaves rather "
            "than judging from the canopy, because the lesion is hidden at the stage it "
            "does the damage.",
        "when_to_call":
            "Call your municipal agricultural technician if panicles are failing to "
            "emerge or emerging partly. Because the same symptoms come from fungi and "
            "from a bacterium, which respond to different treatments, this is a case "
            "where a sample should be looked at rather than treated on sight. " + GAP,
    },

    "Stem Rot": {
        "source": "pacific_pests_stem_rot",
        "identification_cues":
            "Symptoms appear first on the leaf sheaths at the water line during early "
            "heading and grain filling. Hard black fungal bodies (sclerotia) germinate "
            "on the sheath and cause large black spots, which spread into the stem; the "
            "rot causes lodging and, when severe, tiller death. The crop shows chalky "
            "grains and unfilled panicles.\n\n"
            "The diagnostic sign is the sclerotia themselves: look for hard black bodies "
            "on the spots, on both the outside and the inside of the sheaths, and inside "
            "hollow stems. Nothing else on this list leaves those.\n\n"
            "Lookalikes: sheath blight is also at the water line but leaves greyish-white "
            "lesions with brown margins and no hard black bodies. Lodging from stem rot "
            "is lodging with a cause -- if the plants went down with no black sheath "
            "lesions, the Lodging-Physical Damage class is the better fit.",
        "cultural_measures":
            "Before planting, plough the land frequently; applications of lime have been "
            "used to reduce soil pH. During growth, drain the fields periodically to "
            "reduce the number of sclerotia, and use the correct balance between nitrogen "
            "and potassium fertilisers, splitting applications. After harvest, collect "
            "straw and debris and burn it with the stubble, or plough everything into the "
            "soil; rotate with forage or legume crops.",
        "preventive_measures":
            "No variety is highly resistant, though varieties differ in their ability to "
            "withstand lodging -- ask your local agriculture office which of the varieties "
            "available to you stands up best. Sclerotia survive in soil, straw and "
            "stubble and float to the surface during land preparation and irrigation, so "
            "residue handling after harvest is the main preventive lever. " + GAP,
        "monitoring_guidance":
            "Excess nitrogen and too little potassium both favour the disease, and insect "
            "wounds make infection more severe. Check at early heading and grain filling, "
            "at the water line. A stem rot finding is a prompt to look at the N:K balance "
            "and at whether planthopper or armyworm damage came first.",
        "when_to_call":
            "Call your municipal agricultural technician before treating. The cited source "
            "is explicit that cost-effectiveness of fungicides should be weighed "
            "carefully, and that before applying anything you should consider whether "
            "planthopper or armyworm attack, or a nutrient imbalance, is the real driver. "
            "Treating the fungus while the cause is the fertiliser programme wastes the "
            "input. " + GAP,
    },

    "False Smut": {
        "source": "pacific_pests_false_smut",
        "identification_cues":
            "Individual grains are replaced by velvety spore balls, which can be more "
            "than double a normal grain's size. The balls start orange, then turn "
            "greenish-black. Only a few grains on each panicle are affected -- this is "
            "normally a scattered, grain-by-grain finding, not a whole-panicle one.\n\n"
            "Despite the name it is not a true smut. If you are unsure whether grain is "
            "contaminated, the source's method is to wash and collect the spores and "
            "identify them under a microscope.\n\n"
            "Lookalikes: neck and panicle blast also gives a damaged panicle, but blast "
            "blackens the neck or panicle base and leaves unfilled grains rather than "
            "enlarged coloured balls where grains should be.",
        "cultural_measures":
            "Remove the fungal balls as soon as they are seen, and preferably before "
            "they reach the velvety stage, which is when they shed spores. Use moderate "
            "rates of nitrogen and do not over-fertilise; the source names 180 kg/ha as "
            "the ceiling to stay below. Reduce humidity in the crop -- if irrigating, "
            "alternate periods of flooding and drying. After harvest, collect straw and "
            "debris and burn it with the stubble, or plough everything into the soil.",
        "preventive_measures":
            "Use certified seed; if the seed is uncertified the source's treatment is hot "
            "water at 52 C for 10 minutes. Seedborne transmission is suspected but not "
            "well supported, so seed is a sensible precaution rather than the known main "
            "route. Some varieties have low resistance -- check with your local "
            "agriculture office. " + GAP,
        "monitoring_guidance":
            "High temperatures of 25-30 C, high humidity and cloudy weather during "
            "flowering favour the disease, so flowering in a wet overcast spell is the "
            "period to walk the field. Usually a minor disease, but outbreaks in south "
            "and southeast Asia have reached losses of up to 75% through lower grain "
            "weight and smut-ball contamination, so a few balls are worth recording even "
            "when they look harmless.",
        "when_to_call":
            "Call your municipal agricultural technician if balls are appearing on many "
            "panicles rather than a scattered few, or if you intend to keep the crop for "
            "seed -- contaminated seed is the reason this matters beyond the yield. The "
            "cost-effectiveness of fungicide for false smut has been questioned, so that "
            "decision should not be made on sight. " + GAP,
    },

    "Narrow Brown Spot": {
        "source": "uada_cercospora",
        "identification_cues":
            "Narrow, elongated lesions on the leaf blade in shades of brown to "
            "reddish-brown, running parallel to the leaf axis -- roughly 2-10 mm long and "
            "no more than about 1-1.5 mm wide, with a darker centre and a margin that "
            "fades outward. Typically a late-season disease.\n\n"
            "The pathogen (Cercospora janseana) causes three diseases now named by the "
            "tissue affected: narrow brown leaf spot on the blade, Cercospora net blotch "
            "on the sheath (discoloured veins in a net-like pattern), and Cercospora "
            "panicle blight on the panicle rachis and branches. This class covers the "
            "leaf form; if what you see is a netted sheath or a blighted panicle rachis, "
            "the same pathogen is a likely cause even though the model has no class for "
            "it.\n\n"
            "Lookalikes: brown spot is the one to rule out, and shape separates them -- "
            "brown spot lesions are circular to oval, these are narrow and linear. Blast "
            "lesions are spindle-shaped and wider in the middle.",
        "cultural_measures":
            "Nitrogen level affects severity, so the fertiliser programme is the main "
            "cultural lever available in-season. Planting date mattered in the cited "
            "trials, with earlier-planted rice showing less disease than late-planted "
            "rice. " + GAP + " Philippine planting calendars and recommended nitrogen "
            "rates for your variety and season have to come from your technician, not "
            "from the Louisiana and Arkansas trials behind these figures.",
        "preventive_measures":
            "Varieties differ substantially in susceptibility, and in the cited work "
            "resistant cultivars planted early needed no fungicide while the same "
            "cultivars planted late did. Ask your local agriculture office which "
            "available varieties hold up. " + GAP,
        "monitoring_guidance":
            "Shows up late in the season, so it is easy to miss on a crop walked mainly "
            "during tillering. Reported yield losses in susceptible commercial varieties "
            "run from about 10% to 40%, and the disease can carry into a ratoon crop. "
            "Severe cases are also associated with premature ripening, purplish-brown "
            "grain discolouration and lodging, so grain quality is part of what is at "
            "stake, not only yield.",
        "when_to_call":
            "Call your municipal agricultural technician if narrow linear lesions are "
            "widespread late in the season, especially if you are growing the crop for "
            "seed or will ratoon the field. All of the fungicide and variety evidence "
            "behind this entry is from the United States; a Philippine recommendation "
            "has to come from a technician. " + GAP,
    },

    # ------------------------------------------------------------------- viral
    # Tungro, grassy stunt and ragged stunt are the hardest group on this list. All
    # three stunt and discolour the crop, and IRRI reported in 2026 that co-infection
    # of the two stunt viruses produces "Rice Yellowing Syndrome", which looks
    # tungro-like and masks the individual signatures. Every entry below therefore
    # carries the same warning, because a classifier working from one photograph
    # cannot make this call and must not be presented as having made it.
    "Tungro": {
        "source": "philrice_diseases_ph",
        "identification_cues":
            "Local name: tungro, in most dialects.\n\n"
            "Mottled young leaves; older leaves yellow to yellow-orange; stunted growth "
            "with a slightly reduced number of tillers. The field pattern is as "
            "diagnostic as the plant: infected plants first appear scattered a few weeks "
            "after establishment (primary infection), then more appear clustered around "
            "those first plants (secondary infection), and the clusters spread until the "
            "distribution is roughly uniform. Spread by green leafhopper.\n\n"
            "CANNOT BE CONFIRMED FROM A PHOTOGRAPH. Yellow-orange discolouration with "
            "stunting is shared by tungro, rice grassy stunt virus (RGSV), rice ragged "
            "stunt virus (RRSV) and their co-infection. IRRI reported the first "
            "Philippine case of yellowing syndrome after a field initially suspected to "
            "be tungro turned out to be a two-virus co-infection, and recommends "
            "molecular detection (RT-PCR) rather than visual diagnosis. Zinc deficiency "
            "is also described as producing symptoms similar to grassy stunt and tungro. "
            "Treat this class as 'a virus-like yellowing and stunting, probably tungro' "
            "and get it confirmed.",
        "cultural_measures":
            "PhilRice's management list: plant a resistant variety; rotate cultivars; "
            "observe a one-month fallow period in affected areas; practise synchronous "
            "planting; early detection; plough a severely affected field under.\n\n"
            "Synchronous planting and the fallow are community-scale measures -- they "
            "work on the vector's continuous food supply, so one farmer doing them in "
            "isolation gets much less benefit than a barangay doing them together.",
        "preventive_measures":
            "The listed factors that favour the disease are a susceptible variety, a "
            "nearby infected field (especially with green leafhopper present), "
            "continuous and asynchronous planting, absence of a fallow period, and crop "
            "age from vegetative to tillering. Resistant variety plus synchronous "
            "planting plus a fallow is the preventive package; none of it can be applied "
            "once the crop is infected, because there is no cure for a virus in a "
            "standing plant.",
        "monitoring_guidance":
            "The vulnerable window is vegetative to tillering, so the first weeks after "
            "establishment are when walking the field pays. Watch for the pattern rather "
            "than single plants: a few scattered yellow-orange stunted hills that become "
            "a widening cluster is the tungro signature. Record where the first hills "
            "were, since that is what distinguishes primary from secondary spread.",
        "when_to_call":
            "Call your municipal agricultural technician as soon as you see clustered "
            "yellow-orange stunting -- early, while 'plough the affected field under' is "
            "still a decision about part of a field rather than all of it. Ask "
            "specifically whether the field should be sampled for RGSV and RRSV as well "
            "as tungro: the management differs, because the stunt viruses are carried by "
            "brown planthopper and tungro by green leafhopper, and IRRI's position is "
            "that these are not reliably separated by eye.",
    },

    "Grassy Stunt Virus": {
        "source": "irri_yellowing_syndrome",
        "identification_cues":
            "Severely stunted hills with excessive tillering and a very upright growth "
            "habit, giving a grassy, rosette appearance. Leaves narrow, short and "
            "yellowish-green. Infected plants usually survive to maturity but produce no "
            "panicles. Symptoms develop roughly 10-20 days after infection. Transmitted "
            "by brown planthopper.\n\n"
            "The discriminator against ragged stunt is leaf shape and tiller count: "
            "grassy stunt gives narrow yellow leaves and too many upright tillers; "
            "ragged stunt gives twisted leaves with torn-looking edges.\n\n"
            "CANNOT BE CONFIRMED FROM A PHOTOGRAPH. Where both stunt viruses infect the "
            "same plant, IRRI reports the result is yellowing syndrome, which shows "
            "tungro-like yellow-orange discolouration and largely obscures the "
            "narrow-leaf morphology that would otherwise identify RGSV. Zinc deficiency "
            "is also described as giving similar symptoms. Confirmation is by RT-PCR with "
            "virus-specific primers, not by eye.",
        "cultural_measures":
            "There is no treatment for an infected plant; management is directed at the "
            "brown planthopper vector and at the continuity of susceptible crop. The "
            "measures that apply are the same community-scale ones used against "
            "planthopper-borne problems: synchronous planting, a fallow break, and "
            "avoiding the conditions that let planthopper populations build -- which "
            "includes not spraying early-season insecticide that kills the predators "
            "keeping planthoppers down. " + GAP,
        "preventive_measures":
            "Varieties carrying brown planthopper resistance are the main lever, since "
            "cutting vector feeding cuts transmission; IRRI has released varieties "
            "carrying resistance genes. Which of them is available and appropriate for "
            "South Cotabato is a question for your technician. " + GAP,
        "monitoring_guidance":
            "Because symptoms appear 10-20 days after infection, what you see today "
            "reflects vector activity two to three weeks ago -- so a finding is a reason "
            "to check the canopy base for planthoppers now, not only to assess the "
            "affected hills. Infected plants produce no panicles, so every confirmed hill "
            "is a total loss for that hill; counting them gives a direct yield estimate.",
        "when_to_call":
            "Call your municipal agricultural technician on any finding, and ask for "
            "laboratory confirmation rather than accepting a visual call. This matters "
            "more than usual here: tungro is managed against green leafhopper and the "
            "stunt viruses against brown planthopper, so a misidentification sends the "
            "whole response at the wrong insect.",
    },

    "Ragged Stunt Virus": {
        "source": "irri_yellowing_syndrome",
        "identification_cues":
            "Plants severely stunted during early growth. Leaves short and dark green "
            "with serrated, uneven edges; blades twisted at the tip or base, which gives "
            "the leaf a spiral, ragged appearance, and the ragged portions turn yellow to "
            "yellow-brown. Nodal branches are produced at the upper nodes. Panicles are "
            "only partly exserted, with unfilled grains. Transmitted by brown "
            "planthopper, with young nymphs the most efficient transmitters.\n\n"
            "The discriminator against grassy stunt: ragged stunt leaves are twisted and "
            "torn-edged and dark green; grassy stunt leaves are narrow, yellowish and "
            "upright with excessive tillering.\n\n"
            "CANNOT BE CONFIRMED FROM A PHOTOGRAPH. IRRI reports that co-infection with "
            "grassy stunt produces yellowing syndrome -- stunting plus ragged twisted "
            "leaves plus tungro-like yellow-orange discolouration -- and that the two "
            "viruses' symptoms overlap and mask each other, which is why visual diagnosis "
            "is difficult and RT-PCR is recommended.",
        "cultural_measures":
            "No treatment exists for an infected plant. Management targets the brown "
            "planthopper vector and the continuous availability of susceptible crop: "
            "synchronous planting, a fallow break, and protecting the natural enemies "
            "that suppress planthopper populations rather than spraying them out early in "
            "the season. " + GAP,
        "preventive_measures":
            "Brown planthopper resistance in the variety is the main preventive measure, "
            "for the same reason as grassy stunt. Availability for your area is a "
            "question for your technician. " + GAP,
        "monitoring_guidance":
            "Stunting is most severe when infection happens early, so the early "
            "vegetative stage is the period that decides how bad it gets. Partially "
            "exserted panicles with unfilled grains later in the season are the "
            "confirming sign on plants that survived. As with grassy stunt, a finding is "
            "a reason to part the canopy and look for planthoppers at the plant base.",
        "when_to_call":
            "Call your municipal agricultural technician on any finding and ask for "
            "laboratory confirmation, naming both RRSV and RGSV. Co-infection is now "
            "documented in the Philippines, so testing for one virus alone can miss what "
            "is actually in the field.",
    },

    # -------------------------------------------------------------------- pest
    "Stem Borer": {
        "source": "philrice_harmful_organisms",
        "identification_cues":
            "Two signs, depending on crop stage. In young plants, DEADHEART: the central "
            "leaf whorl fails to unfold, turns brownish and dries up. In older plants, "
            "WHITEHEAD: the panicle dries, turns white and carries unfilled grains. "
            "Larvae bore into the stems and hollow them out, so an affected tiller pulls "
            "out easily and is hollow at the base -- that check separates borer damage "
            "from a disease that merely discolours the panicle.\n\n"
            "This class covers several species with the same damage pattern: yellow stem "
            "borer (Scirpophaga incertulas, dilaw na aksip), white stem borer "
            "(S. innotata, puting aksip / puting bagumbong) and striped stem borer "
            "(Chilo suppressalis, guhitang aksip). The damaging stage is the larva; the "
            "plant part attacked is the stem; the vulnerable window is tillering to "
            "reproductive, extending to ripening for striped stem borer.\n\n"
            "Lookalikes: whitehead is also produced by neck and panicle blast, which "
            "blackens the neck instead of hollowing the stem, and by rats, which cut "
            "tillers cleanly at an angle. Pull the tiller and look.",
        "cultural_measures":
            "Cutting leaf tops at transplanting to remove egg masses, and field release "
            "of the egg parasitoid Trichogramma japonicum, are among the options PhilRice "
            "names for stem borer. Plough under stubble after harvest, since larvae carry "
            "over in it, and plant in step with neighbouring fields so the pest does not "
            "have a continuous supply of the right crop stage.",
        "preventive_measures":
            "Plant a variety resistant to the pests common in your area -- PhilRice calls "
            "resistant varieties the first line of defence. Synchronous planting across "
            "neighbouring fields and clean stubble handling are the other two preventive "
            "measures that work at field scale. " + GAP,
        "monitoring_guidance":
            "Weekly monitoring is PhilRice's stated general principle, counting harmful "
            "and useful organisms together and reading them against crop stage, water "
            "status and leaf colour. Count deadhearts during tillering and whiteheads "
            "after heading, as a percentage of tillers, so a decision rests on a number. "
            "Note that whiteheads counted after heading record damage already done -- the "
            "number guides next season, not this one.",
        "when_to_call":
            "Call your municipal agricultural technician before any insecticide "
            "decision. PhilRice's position is that chemical control should be used only "
            "where essential, and early-season spraying is counterproductive because it "
            "kills the parasitoids and predators that suppress borers and planthoppers. "
            "An economic threshold for your variety and season has to come from a "
            "technician. " + GAP,
    },

    "Rice Black Bug": {
        "source": "philrice_harmful_organisms",
        "identification_cues":
            "Scotinophara coarctata; Filipino name itim na atangya. Both nymphs and "
            "adults damage the crop, attacking stems, tillers and panicles from seedling "
            "through flowering. Signs are deadheart, reddish-brown leaves and reduced "
            "tillering. In severe infestations young plants are killed and the whole "
            "field can look burnt -- 'bug burn'.\n\n"
            "The bugs themselves are the confirmation: dark, shield-shaped, and found low "
            "on the plant. They are attracted to light, so a light trap near the field "
            "catching large numbers is corroboration.\n\n"
            "Lookalikes: bug burn resembles hopperburn from planthoppers, and both show "
            "patches of browning and collapse. Part the canopy and look at what insect is "
            "actually at the plant base -- black bugs are larger, dark and shield-shaped; "
            "planthoppers are small, brown and numerous. Reddish-brown leaves plus "
            "deadheart points to black bug.",
        "cultural_measures":
            "Synchronous planting with neighbouring fields and a fallow break, so the "
            "population does not carry continuously from one crop to the next. Light "
            "traps are used both to monitor and to reduce adult numbers, because the "
            "adults fly to light. Drain and dry the field where the crop stage allows, "
            "and handle stubble after harvest rather than leaving it standing. " + GAP,
        "preventive_measures":
            "Plant a resistant variety where one is available for your area; PhilRice "
            "names resistant varieties as the first recommendation for its five major "
            "insect pests, of which rice black bug is one. " + GAP,
        "monitoring_guidance":
            "PhilRice cites a yield reduction of roughly 15-23% for every 10 rice black "
            "bugs detected per rice stem, so counting bugs per stem is the measurement "
            "that matters, not the area of browning. Count at the plant base, on several "
            "hills across the field. The vulnerable window runs from seedling to "
            "flowering, so monitoring should not stop after establishment.",
        "when_to_call":
            "Call your municipal agricultural technician if counts approach the order of "
            "10 bugs per stem, or if browning patches are spreading. Rice black bug "
            "appears on BPI's list of pests forecast to threaten Philippine rice "
            "production, so a local outbreak may already be known to your office and "
            "there may be an area-wide response to join. " + GAP,
    },

    "Rice Bug": {
        "source": "philrice_field_guide_organisms",
        "identification_cues":
            "Leptocorisa oratorius; Filipino name atangya. Slender bugs about 15 mm "
            "long; nymphs green, adults greenish-brown. They release an odorous "
            "substance when handled that stains fingers orange -- the smell and the stain "
            "are a reliable field confirmation.\n\n"
            "Damage is to the grain: the bugs suck sap from developing milky grains, "
            "giving discoloured or shrivelled grains and an off-odour or off-flavour in "
            "the rice and straw. Before grain formation they feed on shoots and leaves. "
            "Nymphs cause more damage than adults. The vulnerable window is flowering to "
            "the milky stage.\n\n"
            "Lookalikes: unfilled or discoloured grain is also produced by neck and "
            "panicle blast, false smut, stem rot and birds. Rice bug damage comes with "
            "the bugs present at flowering and the characteristic smell; it does not "
            "blacken the neck or leave spore balls.",
        "cultural_measures":
            "Remove grassy weeds, which host the bugs between crops, and avoid staggered "
            "planting so flowering is not continuously available across neighbouring "
            "fields. Net and handpick the bugs, or use sticky-coated baskets or "
            "attractants -- the field guide lists these as practical options at small "
            "scale.",
        "preventive_measures":
            "Awned, or bearded, varieties are resistant, and varieties whose panicles "
            "stay enclosed in the leaf sheath longer offer some mechanical resistance. If "
            "rice bug is a recurring problem on your farm, variety choice is the "
            "preventive measure with the clearest basis. " + GAP,
        "monitoring_guidance":
            "Walk the field at flowering and through the milky stage, which is the only "
            "window in which this pest matters. No action threshold is given in the cited "
            "guide, so a count per hill or per sweep should be recorded and discussed "
            "with your technician rather than compared against a number from this "
            "database. " + GAP,
        "when_to_call":
            "Call your municipal agricultural technician before spraying at flowering. "
            "Two specifics from the guide are worth repeating to them: granular "
            "insecticides are ineffective against this pest, and application timing is "
            "early morning or evening on calm days. Product choice remains a "
            "technician's decision. " + GAP,
    },

    "Leaf Miner-Whorl Maggot": {
        "source": "philrice_field_guide_organisms",
        "identification_cues":
            "Hydrellia philippina; Filipino names langaw palay, langaw bukid. Adults are "
            "dull grey flies, females 1.8-2.3 mm. The damaging stage is the larva, which "
            "feeds inside unopened leaves.\n\n"
            "Signs: pinhole feeding spots, and white-to-yellowish linear patches near the "
            "leaf edges. Leaves may be distorted or break. Plants are stunted with few "
            "tillers. The vulnerable window is seedling to tillering, but the maggots can "
            "also damage the boot leaf and developing panicle, causing partial grain "
            "filling and delaying maturity by up to two weeks.\n\n"
            "Lookalikes: the pale linear patches can read as a nutrient problem or as "
            "early leaf disease. The discriminator is that the damage is inside leaves "
            "that had not yet opened, so it appears as the leaf unfurls, in streaks "
            "parallel to the leaf -- not as spots scattered across an expanded blade. "
            "Thrips also roll and streak seedling leaves; thrips damage rolls the leaf "
            "inward from the margin and dries it from the tip down.",
        "cultural_measures":
            "Transplant older seedlings, 25-30 days, and drain the field at 3-4 day "
            "intervals during the first 30 days after transplanting -- draining is the "
            "central measure, because the fly needs standing water. Direct seeding and "
            "dense planting reduce the impact, and azolla cover is listed as an option. "
            "Fishmeal baits attract the adults.",
        "preventive_measures":
            "Seedling age at transplanting and early water management are the preventive "
            "levers, and both are decided before or at transplanting. The guide also "
            "mentions soaking seedlings in a systemic insecticide and zinc oxide slurry "
            "in the seedbed; that is an input decision for a technician and the product "
            "is deliberately not named here. " + GAP,
        "monitoring_guidance":
            "The window is the first weeks after transplanting. Check newly unfurling "
            "leaves rather than old ones. Damage is usually outgrown by a healthy crop, "
            "so the question to answer is whether plants are recovering and tillering, "
            "not simply whether the marks are present.",
        "when_to_call":
            "Call your municipal agricultural technician if plants are not recovering by "
            "the end of tillering, or if damage reaches the boot leaf, since that is the "
            "form that costs grain. Note the guide's timing constraint: foliar sprays are "
            "effective only at 1-2 weeks after transplanting, so a spray decision made "
            "later is unlikely to help. " + GAP,
    },

    "Thrips": {
        "source": "tnau_rice_pests",
        "identification_cues":
            "Stenchaetothrips biformis. Adults slender, dark brown, 1-2 mm, winged or "
            "wingless -- small enough that the damage is usually seen before the insect. "
            "Nymphs and adults lacerate tender leaves and suck the sap.\n\n"
            "Signs: yellow or silvery streaks on the leaves of young seedlings; leaves "
            "roll inward along the margins; terminal rolling and drying of leaves from "
            "the tip downward, which is the typical symptom. Severely infested leaf tips "
            "wither. Damage occurs in both the nursery and the main field, and in severe "
            "cases a nursery can dry up and fail to produce usable seedlings. Unfilled "
            "grains are reported where infestation continues to the panicle stage.\n\n"
            "Lookalikes: whorl maggot also marks seedling leaves, but with pinhole spots "
            "and patches near the edges rather than inward rolling and tip-down drying. "
            "Drought and salinity also roll and dry leaf tips -- and because thrips "
            "damage is itself most severe under water stress, both can be present at "
            "once. Check whether the field is short of water before treating the insect.",
        "cultural_measures":
            "Submerging the infested field is the measure the cited sources agree on, "
            "reported as flooding to submerge for about two days. Since the damage is "
            "worst under water stress, maintaining water is both the control and the "
            "prevention. Remove grassy weeds in and around the nursery.",
        "preventive_measures":
            "The crop is most susceptible in the nursery and the first roughly 23-25 days "
            "after sowing or transplanting, so protecting the seedbed and keeping it from "
            "drying out is where prevention happens. " + GAP,
        "monitoring_guidance":
            "Check the nursery and the newly transplanted crop, looking at the youngest "
            "leaves. The thresholds in the cited Indian material are 60 thrips per 12 wet "
            "hand sweeps in the nursery, or rolling of the first and second leaves in 10% "
            "of seedlings. Record counts in that form so a technician can work with them, "
            "but treat the numbers as indicative: they are economic threshold levels set "
            "for Tamil Nadu, not Philippine recommendations. " + GAP,
        "when_to_call":
            "Call your municipal agricultural technician if a seedbed is drying out "
            "under infestation, since the whole nursery is at risk. The cited sources "
            "name insecticides that are restricted or banned in several countries, "
            "including the Philippines; none is reproduced here, and any product decision "
            "must come from a technician working off the current DA/FPA registered list. "
            + GAP,
    },

    # ------------------------------------------------- abiotic, physical, weed
    # Like "Nutrient Deficiency" in the sibling script, this class names a category
    # rather than a cause. The entry's main job is to say so, so the UI does not
    # present a category as a diagnosis.
    "Abiotic Stress": {
        "source": "philrice_diseases_ph",
        "identification_cues":
            "General, non-infectious damage: discolouration, wilting, stunting, drying "
            "or dieback that does not fit a pathogen or an insect, judged against healthy "
            "plants of the same variety and age in the same field.\n\n"
            "IMPORTANT: this class does not say WHAT the stress is. PhilRice's diagnostic "
            "framework separates biotic agents (pathogens) from abiotic, non-infectious "
            "agents, and the abiotic group covers distinct causes with different "
            "corrections: water deficit, submergence and stagnant water, salinity, heat "
            "and cold, nutrient toxicity such as iron or aluminium, chemical or herbicide "
            "injury, and typhoon or wind damage. Nothing in a photograph separates them.\n\n"
            "Where to look instead: if the field was submerged, the Flooding class "
            "carries drafted guidance. If the problem is a deficiency rather than a "
            "stress, Nutrient Deficiency carries drafted guidance. If the crop is flat, "
            "Lodging-Physical Damage is the better class. Use this class when the damage "
            "is non-infectious but none of those fit.\n\n"
            "What actually identifies the cause, per PhilRice, is field history rather "
            "than appearance: what was done in the previous and present cropping season, "
            "the age of the plants at onset, the variety, the condition of the field, the "
            "cropping system, the farm inputs used, and the farmer's own account. Collect "
            "those before concluding anything.",
        "cultural_measures":
            "No single correction applies, because the causes differ. The honest action "
            "at this point is diagnostic, not corrective: record the field history above, "
            "note where in the field the damage sits (edges, low spots, downwind side, "
            "near a drain or a sprayed boundary), and check whether the pattern follows "
            "water, soil or wind rather than spreading plant to plant. A pattern that "
            "follows the land is abiotic; a pattern that spreads outward from a focus is "
            "usually not. " + GAP,
        "preventive_measures":
            "Depends entirely on which stress it turns out to be, so prevention cannot be "
            "stated here without knowing the cause. " + GAP,
        "monitoring_guidance":
            "PhilRice's standing advice is to observe the field regularly and look for "
            "patterns. For abiotic damage the pattern is the evidence, so note its "
            "position and extent on each visit and whether it is expanding. Photograph "
            "the same spots across visits: abiotic damage often stabilises once the "
            "stress passes, while disease keeps advancing, and that difference is "
            "visible over a week even when a single photograph is ambiguous.",
        "when_to_call":
            "Call your municipal agricultural technician, and treat this class as a "
            "prompt to do so rather than as a finding you can act on. Bring the field "
            "history, not just the affected plants. Ask specifically about a soil test "
            "where salinity or a toxicity is plausible, and mention any herbicide or "
            "other chemical applied in this or the previous season, since injury from "
            "those is a common cause that farmers do not usually volunteer.",
    },

    "Vertebrate Damage": {
        "source": "philrice_field_guide_organisms",
        "identification_cues":
            "Two different animals, with different signs.\n\n"
            "RATS (Rattus argentiventer; daga): tillers cut near the base at about a "
            "45-degree angle -- the clean angled cut is the signature. Other signs are paw "
            "marks and runways on wet soil, heaps of soil along the bottom of bunds, "
            "nests, and hulls floating on the water after harvest. Damage concentrates in "
            "the centre of the field, producing 'eat-outs'. Seedbeds can be heavily "
            "damaged and seedlings eaten after transplanting. Damage is higher early in "
            "the season than at ripening, and plants near uncultivated areas, roads and "
            "canals are worst affected.\n\n"
            "BIRDS (sparrow / maya): flocks feed at the milky or soft-dough stage and cut "
            "about half the grain. Birds also take grain from nursery beds and during "
            "threshing and storage. Most active in early morning and late afternoon, in "
            "flocks, near houses and farm or coconut canopies.\n\n"
            "Lookalikes: cut tillers and whiteheads are also produced by stem borer, but "
            "a borer-damaged tiller is hollowed and pulls out easily rather than being "
            "cut cleanly at an angle. Missing hills with floating plant fragments is "
            "golden apple snail damage, not vertebrate.",
        "cultural_measures":
            "For rats, the field guide's measures are: use a community approach and plant "
            "at the same time as neighbours; remove weeds along dikes and canal banks; "
            "build paddy dikes about 6 inches high and 8 inches wide in irrigated rice; "
            "flood or dig out burrows; use cage traps and snap traps along dikes; and "
            "establish a Trap Barrier System one month before cropping, since catches "
            "peak during land preparation. It notes that scarecrows and flags have little "
            "effect and mechanical barriers are of limited value, and that a flame "
            "thrower should be used only with caution because it kills non-target "
            "organisms too.\n\n"
            "For birds, scaring them away is described as the only practical solution.",
        "preventive_measures":
            "Rat control is a community measure before it is an individual one: "
            "synchronous planting and clearing harbourage along dikes and canals work at "
            "a scale one farmer cannot reach alone, and the Trap Barrier System is set up "
            "a month ahead of cropping. For birds, varieties with long serrated awns "
            "discourage feeding.",
        "monitoring_guidance":
            "The field guide's principle for rats is that it is the number remaining in "
            "the field that reduces yield -- so judge control by what is still there, not "
            "by what was caught. Check bunds and canal banks for fresh runways and soil "
            "heaps, and the field centre for eat-outs. Rats live a year or more and a "
            "female can have up to four litters a year averaging six young, so a small "
            "population left alone does not stay small. For birds, the milky to ripening "
            "window is what matters.",
        "when_to_call":
            "Call your municipal agricultural technician if eat-outs are appearing in the "
            "field centre or damage is spreading from neighbouring land, since the "
            "effective response is area-wide and your office can coordinate it. "
            "Rodenticides are the one place the field guide gives timing: acute poisons "
            "only before seedbedding or transplanting and only where populations are "
            "extremely high, chronic rodenticides from transplanting until two weeks "
            "before harvest, with 5-10 baiting stations per hectare alongside dikes. "
            "Product selection and safe handling are a technician's decision; nothing is "
            "named here. " + GAP,
    },

    "Weed Presence": {
        "source": "philrice_weeds_lowland",
        "identification_cues":
            "Plants other than rice growing in the stand. This class records that weeds "
            "are present; it does not identify the species, and species is what "
            "determines the management -- PhilRice's position is that knowledge of proper "
            "weed identification is critical to selecting and implementing effective weed "
            "management.\n\n"
            "Worth separating by eye where possible: grasses (barnyardgrass, Echinochloa, "
            "is the one most often named in Philippine rice), sedges (including Cyperus "
            "rotundus), and broadleaves. Weedy rice is the hardest case, because it looks "
            "like the crop -- it is closely related to cultivated rice, competes for "
            "nutrients, and heavy infestation can cause total crop loss through "
            "competition and lodging.\n\n"
            "Lookalikes: a detection of Weed Presence on an aerial or wide shot may be "
            "recording nothing more than bund vegetation or a field margin. Check that "
            "the weeds are inside the stand before treating this as a crop problem.",
        "cultural_measures":
            "Timing is what the Philippine work emphasises: there is a critical period "
            "during which weeds must be removed, and control outside it is largely wasted "
            "effort. Philippine research on Cyperus rotundus under flooded conditions "
            "established critical periods of control for transplanted and wet "
            "direct-seeded rice specifically because that information was not previously "
            "known, which is a measure of how species- and system-specific this is.\n\n"
            "Land preparation timing combined with weed control reduced the dominant weed "
            "species in Philippine rainfed lowland trials, and good early water "
            "management -- proper levelling and water in the first weeks -- suppresses "
            "weeds before they establish. Hand weeding remains effective; PhilRice "
            "promotes integrated weed management rather than reliance on any single "
            "method.",
        "preventive_measures":
            "Use clean certified seed, which is the main route by which weedy rice is "
            "introduced, and level the field so water can be managed uniformly. Where "
            "upland crops can follow rice, crop rotation allows manual weeding and "
            "widens the control options. Herbicide resistance is already documented in "
            "Philippine rice weeds -- Sphenoclea zeylanica resistant to 2,4-D was "
            "recorded in Bulacan after prolonged use of that one herbicide -- so rotating "
            "methods rather than repeating one is itself a preventive measure.",
        "monitoring_guidance":
            "What matters is weed presence during the critical period for your "
            "establishment method, so record the crop's age in days after transplanting "
            "or sowing alongside the finding; a weed observation without a date is of "
            "little use. Note which of the three groups dominates, since the control "
            "differs.",
        "when_to_call":
            "Call your municipal agricultural technician to identify the species and set "
            "the critical period for your establishment method and season, and raise it "
            "early -- once the critical period has passed, the yield is already lost and "
            "control that season only limits seed set for the next one. Flag any suspected "
            "weedy rice specifically. Herbicide selection, rate and timing are a "
            "technician's decision and no product is named here; given the documented "
            "resistance, repeating whatever was used last season is the thing to ask "
            "about rather than assume. " + GAP,
    },
}


def upsert_sources(session) -> dict[str, int]:
    """Create any SOURCES row that isn't there yet; return key -> id.

    Matched on (title, publisher) like the sibling script, so re-running does not
    duplicate a source, and a source shared with load_knowledge_drafts.py is reused
    rather than inserted twice.
    """
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
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would change and write nothing, including no sources")
    args = parser.parse_args()

    cfg = get_config()
    init_engine(cfg.sqlalchemy_uri)
    session = SessionLocal()

    source_ids = {} if args.dry_run else upsert_sources(session)

    written = skipped_reviewed = skipped_draft = missing = collided = 0
    # Same guard as the sibling: conditions.code is utf8mb4_general_ci, so two keys
    # differing only in case resolve to one row. Writing both would violate
    # uq_kb_condition, so the first wins and the collision is reported, not hidden.
    handled: dict[int, str] = {}
    for code, draft in DRAFTS_2.items():
        cond = session.execute(
            select(Condition).where(Condition.code == code)
        ).scalar_one_or_none()
        if cond is None:
            print(f"  no such condition, skipped: {code}")
            print("    run scripts.import_conditions scripts/conditions_modelA_v2.csv first")
            missing += 1
            continue
        if cond.id in handled:
            print(f"  same condition as '{handled[cond.id]}' (case-insensitive code), "
                  f"skipped: {code}")
            collided += 1
            continue
        handled[cond.id] = code

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

        if args.dry_run:
            was = row.content_status if row is not None else "no row"
            print(f"  would write as DRAFT: {code}  (currently {was})")
            written += 1
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
            session.flush()
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        print(f"  written as DRAFT: {code}")
        written += 1

    if args.dry_run:
        session.rollback()
    else:
        session.commit()
    SessionLocal.remove()

    print()
    label = "DRAFT rows that would be written:" if args.dry_run else "DRAFT rows written:  "
    print(f"{label} {written}")
    print(f"left alone (REVIEWED): {skipped_reviewed}")
    print(f"left alone (DRAFT):    {skipped_draft}")
    print(f"duplicate condition:   {collided}")
    print(f"condition not found:   {missing}")
    if args.dry_run:
        print()
        print("DRY RUN -- nothing was written and no sources were created.")
        return 0
    print()
    print("These rows are DRAFT. They are summarised from published sources, not")
    print("reviewed agronomy, and no farmer should act on them yet. A technician or")
    print("adviser must check each entry against local practice, fill in every field")
    print("marked NEEDS LOCAL INPUT, and only then set content_status='REVIEWED'.")
    print()
    print("Five of these sixteen are sourced from outside the Philippines (Narrow Brown")
    print("Spot, Sheath Rot, Thrips, and the two stunt viruses in part). Their locator")
    print("field says so. Those need the closest review: thresholds, varieties and")
    print("products in the originals are not Philippine recommendations.")
    print()
    print("Three classes name a category, not a cause, and say so in their own text:")
    print("Abiotic Stress, Weed Presence, and -- in the sibling script -- Nutrient")
    print("Deficiency. The UI must not present those as a diagnosis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
