# AGRISCAN Model A — Step 4, Tier-1 edition.
#
# Drop-in replacement for the Step 4 cell in agriscan_modelA_v1.ipynb. Run Steps 0-3
# first, in the same Colab session, and set RUN = 'modelA_v3' in Step 2.
#
# WHY THIS EXISTS
#   modelA_v2 trained on 25 classes and scored 0.876, but scripts/register_model
#   refuses to promote it: it matches class names against the `code` column of the
#   conditions table as exact strings, and not one of the 25 matched. That check is
#   deliberate. A promoted model whose labels are misaligned files every detection
#   under the wrong condition, and nothing in the interface would show it.
#
#   So the folders are renamed to the Tier-1 codes the database already holds, and
#   the 40 source folders are collapsed onto them.
#
# WHY EIGHT CLASSES AND NOT NINE
#   The taxonomy has nine codes, but `unknown` is not trained. It is what the worker
#   assigns when the model is not confident enough — see AGRISCAN_CONF_THRESHOLD
#   (0.50) and AGRISCAN_MARGIN_THRESHOLD (0.10) in app/config.py, and the
#   low_confidence branch in worker/run.py. Training an `unknown` class on the ~20
#   leftover folders would make one incoherent bucket of Tungro, stem borer, false
#   smut, weeds and rodent damage; it would dominate the loss and teach the model
#   nothing. Leaving those folders out and letting the confidence gate produce
#   `unknown` is both better ML and what the system was designed to do.
#
# WHAT GETS LEFT OUT
#   Roughly 2,300 images in conditions outside Tier 1. They are not wasted — they are
#   what a Tier-2 taxonomy would be built from, once there are condition codes and
#   knowledge base entries to receive them. Right now there are neither.

import hashlib, random, collections, shutil, os
from pathlib import Path

SRC, OUT = Path('/content/raw'), Path('/content/dataset')
IMG_EXT = ('.jpg', '.jpeg', '.png')
random.seed(42)

# Drive folder -> conditions.code. The keys must match the folder names exactly,
# including the 'Phosphorus Defiency' misspelling as it stands in Drive.
TIER1 = {
    # healthy
    'Healthy Rice plant':        'healthy',

    # bacterial_leaf_blight — Xanthomonas oryzae pv. oryzae.
    # Leaf streak is a different pathovar, but the field guide treats the two
    # together and the recommendation is the same. Flag this in the methodology.
    'Bacterial Leaf Blight':     'bacterial_leaf_blight',
    'Bacterial Leaf Streak':     'bacterial_leaf_blight',

    # rice_blast — one pathogen, four plant parts.
    'Leaf Blast':                'rice_blast',
    'Rice Blast':                'rice_blast',   # nested under Leaf Blast/
    'Blast':                     'rice_blast',
    'Neck Blast':                'rice_blast',
    'Panicle Blast':             'rice_blast',
    'Collar Blast':              'rice_blast',

    # brown_spot — Bipolaris oryzae. Narrow brown spot is Cercospora, a different
    # fungus with a near-identical field response. Flag it too.
    'Brown Spot':                'brown_spot',
    'Narrow Brown Spot':         'brown_spot',

    # hopperburn — the damage, not the insect. Both hoppers cause it.
    'Brown Planthopper':         'hopperburn',
    'Green Leafhopper':          'hopperburn',

    # nitrogen_deficiency — nitrogen only. Zinc and phosphorus deficiency look
    # different, have different corrections, and have no condition code yet.
    'Nitrogen Deficiency':       'nitrogen_deficiency',

    # lodging — flattened crop. Weather damage is the usual cause of lodging here,
    # but the folder may also hold hail and wind shredding, which is not lodging.
    # Check a sample before trusting this one.
    'Lodging':                   'lodging',
    'Physical Weather Damage':   'lodging',

    # flooding
    'Flooding':                  'flooding',
}

CAP = 450        # ceiling per class, stops one class dominating the loss
MIN_CLASS = 40   # floor: below this a class cannot be trained or scored

pool, seen, dupes, cross, unreadable = collections.defaultdict(list), {}, 0, [], 0
excluded = collections.Counter()

for top in sorted(SRC.iterdir()):
    if not top.is_dir():
        continue
    for dirpath, _, files in os.walk(top):           # recursive: Leaf Blast/Rice Blast
        folder = os.path.basename(dirpath)
        cls = TIER1.get(folder) or TIER1.get(top.name)
        for fname in files:
            if not fname.lower().endswith(IMG_EXT) or fname.lower().startswith('aug_'):
                continue
            if cls is None:
                excluded[top.name] += 1
                continue
            f = Path(dirpath) / fname
            try:
                h = hashlib.md5(f.read_bytes()).hexdigest()
            except Exception:
                unreadable += 1
                continue
            if h in seen:
                dupes += 1
                if seen[h] != cls:
                    cross.append((cls, seen[h], fname))
                continue
            seen[h] = cls
            pool[cls].append(f)

print(f'removed {dupes} duplicates ({unreadable} unreadable)')
print(f'{len(cross)} were cross-class duplicates — the same image under two labels')
for cls, other, fname in cross[:10]:
    print(f'   CROSS-CLASS: {cls} vs {other} -> {fname}')
if len(cross) > 10:
    print(f'   ... and {len(cross) - 10} more')

print(f'\nnot in Tier 1, excluded ({sum(excluded.values())} images):')
for folder, n in excluded.most_common():
    print(f'   {n:5d}  {folder}')

too_small = {c: len(f) for c, f in pool.items() if len(f) < MIN_CLASS}
if too_small:
    print(f'\nbelow MIN_CLASS={MIN_CLASS} — these cannot be trained or scored:')
    for c, n in sorted(too_small.items(), key=lambda kv: kv[1]):
        print(f'   {n:5d}  {c}')
    print('   STOP. A Tier-1 code with too few images has to be reported as out of')
    print('   scope in the paper, not quietly trained on a handful of photos.')

missing = sorted(set(TIER1.values()) - set(pool))
if missing:
    print(f'\nno images at all for: {", ".join(missing)}')

if OUT.exists():
    shutil.rmtree(OUT)

print(f'\n{"conditions.code":24s} {"total":>6s} {"train":>6s} {"val":>5s} {"test":>5s}')
grand = 0
for cls, files in sorted(pool.items()):
    random.shuffle(files)
    files = files[:CAP]
    n = len(files)
    cuts = {'train': files[:int(.7 * n)],
            'val':   files[int(.7 * n):int(.9 * n)],
            'test':  files[int(.9 * n):]}
    for split, items in cuts.items():
        dst = OUT / split / cls
        dst.mkdir(parents=True, exist_ok=True)
        for f in items:
            shutil.copy2(f, dst / f.name)
    grand += n
    flag = '  <-- test split too small to score' if len(cuts['test']) < 8 else ''
    print(f'{cls:24s} {n:6d} {len(cuts["train"]):6d} '
          f'{len(cuts["val"]):5d} {len(cuts["test"]):5d}{flag}')

print(f'\nclasses: {len(pool)} | images: {grand} | mean per class: {grand / max(len(pool),1):.0f}')
print('\nClass folder names are conditions.code values, so register_model will accept')
print('these weights. `unknown` is assigned by the confidence gate at inference and')
print('is deliberately not a trained class.')
