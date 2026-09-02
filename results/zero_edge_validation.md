# Zero-edge proxy validation

Diagnostic only. No E0, no scoring, no AUC, no model.

## Spine

- Digest prefix: `6129eb13d6a4` (full `6129eb13d6a46457cd60627372b7b5479df0aa1f4efc9bbb70adc17826c64000`)
- Counts: train-benign=562 / test-benign=141 / test-malware=1700
- Sample: 50 benign + 50 malware, seed=42, from 2403 eligible
- Benign app_ids (sha256):
  - `02122C1CC9D9F9A911C58B901663A5C244C21530AD3AB053568E3064F967EE39`
  - `0909DE0D3CEC99F2F54C3AE30906CFC775A3F05A75EF541150F1587A73563634`
  - `0BBF0829EB8E973F3ECCF005E0EDA5D3A5CF20A5E95A4E3C5EE226B450DAE31D`
  - `0CD847919F16761E7705DA96BDECE408700C430C0FC9E2E06454EA40A4A88407`
  - `0DA1B5FEBA812D1318762AAFA8540CF0B3D204A3CB1D4B5CAA65E9A73EE71394`
  - `0F03CF62EBE16C46A91EF63D0D77CF2DE918933D1AD4CA192226E2DF2FF8CD76`
  - `14EA7EAF5270720A6B61F614B8E45AE207A41CD49E3D9036AF24A05ECE185DFC`
  - `1AA519B25620EC2584AA89D097A93C4F87E646596606E246C8265C100B9C5CBC`
  - `24B707104D7A18D604E132E3179B95AB9EE0C9A9FD2273AF4AEF3ADF21A887CC`
  - `27448A23083D96A49286338E610479892E64B44D3A356BB8DDF9BC73BFF36E45`
  - `2A025C2D9F10365F3DDDC3891C774F3BAA4E2ABD5ADE5EC99D9DE7DCEB5E7B72`
  - `2D45FBF1651647B7BBFF26A126798F8C3642121D34B362BB6C369EA02DF7CAC3`
  - `309143F1F0F6F0B38951C3CE3D51865963F95C85B3877BE422F0E8703DE70EC2`
  - `30F441FDFD16F05CB1307375881D36C442839B786374969E949BF91666DE01EF`
  - `329729931D12CB3E34603707A159FEED2BE8EBC6C469F595D71E0A286A4D0BCC`
  - `371594CC83B1237C1E7C0B21E2BB92B86CE17E3EABA284B8D5256D24A3962A69`
  - `3DE645A5B2EB1383DF232EC1A8F0A3FA29654B8EBCBF3D71C605A2407FE8E7A5`
  - `4316B03B28DBDF4222B046617D336450FD31331D3C087EAA3C9F741BFA80B1BA`
  - `44BAA5FB6043E7EBEB52561A28DAC61C02E493F780B7A0BD5DF553C3BBB10708`
  - `4685289644B623228504FFDA4AE8B1B577C0BC8C5C16EEA4DAC1C0F3EDF081D2`
  - `4F802185A14120BD953A34935A83A995BA4A702EFD52B9D42330F9CE79E5D485`
  - `5185323B7AF46F228CBF249CB34AA1E3E885EDBC27F86266BC4239E0FC00E990`
  - `64337EE37E08B91EC72623C1D08C7CB63E21C37A3A9EB171935C82536F0D74EA`
  - `6AE5BCC6E666845538D9210191258897195A990EA50B109E40353814CA2B4607`
  - `6C04D3B5CB3B3DE263161EAF277CB1432694FCDDD4D2C0EF9E793CDB0CA99A8D`
  - `6D68186F59DD92FC6DD96CAD743B85976CA5861430328EC8767AB60CD1C8BF70`
  - `6D9C23B98C26EB7B7BD0D958F77960C49FFB26487D5A9D8913CA2F86980C5D53`
  - `722642C74F4F999B3C90A95BFFF703F3C9D1658C58D21EF69B53F9BE798A7225`
  - `7785E1DDCAD8B073BA0DFF12BBF6C6A194843613FE0620C683DBE7F5EE5516DA`
  - `7BFA10FD0A5DC6C21E4A6080C4BE850468413B3BF5A94B3C752C48ECD0BA40E3`
  - `7EE77E46C02DE8E5ED22C94FA85BC21E815768D417DEC1CE70388C55BB0E85BF`
  - `81D05D0E4CE4CF954455298A534518F95AA7113777CDA71D6C14C61D862C15A6`
  - `82E18332C0325A6A1DCB53F4F8AD780A83E4AF6B8342DAD2F49D8EB1D884CA6B`
  - `8C4445F90855588D536A3B5F4818583136FA2F856DE34703BE5C0CB20AC57F18`
  - `8F00E09041FBB9C5A8AC1EC4A9CE33940E4761FD197F47089FA2B8833B3509DA`
  - `98CEF37C75554D8833740136C4724B79BFBFFEA635EB3E0D77D510465DD35F2F`
  - `A809B86328C1A17773AC0D17A8539C778943A5250336F0C850949A284C883A72`
  - `AB9363F2182861BF526D68EA7CE1F8F37DCD647EA365BEF1D166FE25DC6F84E7`
  - `AD312B18C97552124F07EF9739B09B350826987CE715EC84E916DB220DC2A6AC`
  - `B125FBF2F32E3F846A546222A3E78887234CE8F305B5058AEEE3A2271A21631B`
  - `B8418CB2D49037B6468C62512844881B8A5ADCE4B49BF632206DD809B907892D`
  - `B8D5027DDEE490DF3429F4BB03025ED49703273265FE6908D8A08CDC71131028`
  - `B96C0818FC779106B3FEDA5241928A1A2072AC8BB284464224FE5CE09FCF40E1`
  - `BEDAD48F04FF6B2EA400739D93C1DDB459F5D96700C77F0220499214B3FFE6C7`
  - `CA99D1F959970A8365C1CF27745E4DA58E17581FEBDEC65137C7EDA932B1912D`
  - `CFD8F8FD2DECE036FBD3DB5CB3A4CF7C53AE8161196DD56E728C75D8FC2B3687`
  - `D942002F584C199AAFBDF28F577EAA55D2ABE433CDC240A20120D06474B9CD7E`
  - `DF3773E09FE9EF6373799897B7A5504BAB5DAB128DDEDDDA3A25B793197D3D50`
  - `E3A82355EFA27F1660C6FFD1AF993CC147564AAE84490D1F7AA4238843F14613`
  - `F436D1F3F939AB829D43FD955C01D42958EE912560D05AA2C0C362D54AEFAE50`
- Malware app_ids (sha256):
  - `00691DB398704A9745E89C0D81D68FCC924FBB66DACAAAD0A58EABF781B693D4`
  - `00806B329D6E1451C087591533C1AD6BCE846E9E5A2A3518D0468DB5267F4D06`
  - `00A401E3564C98091FB54B6BCA141DEB679EA9478C1C6FFD6865C2BB7173740B`
  - `00A654964741571E8DF79E6FE278858174431D77EC330B6447F8CECF12DCF8B0`
  - `00B8AA518F04382EF48F4A37E0EFB6326D318FC5265507AF3B5A6824ACB14ADB`
  - `00ED13299F302D53827C3D9D89C2231AC82B60EADFBA8901E206F5DD3766FFFF`
  - `016E2CD8FAC8B1A5D43E86B49F8D619DCFECEE360B7CDBCB663E7FACCE260466`
  - `016E9C05D979E10CD3D9DEB3FEE5FAB2A513D01A9B50DBB4F067A67C451BF950`
  - `017AB6028D3D132068FE63BE09DDE502B60F8E910829C370DC2EB738DC829742`
  - `01A03D854323C9A1A35EB18E9CB04E820E41FC087731A4CD3509F70632290145`
  - `01C64B8BE315791B6AC6D3573BC09EF1E662CB974B313616F9725718195D451D`
  - `01D6D002DF0E9B131FAC72A89DEDED1DA580CCF00FE2125EF2B1F0E0AA5E220D`
  - `01EDAD70FA159A8319F497796AB8617252836B4FED8EB90185B417F01CED7B40`
  - `01F76024F82ED6BEC30A51C8C80749D01A284BB24AB8FCFD0C2A663AB8F6C99A`
  - `02072F02710156A0F06EE281BE3705783074990CFB5E48BF478B766F95B181C0`
  - `023C7788C9E87D58A34DF03C214966FA7E79B26FCFA73B297B013F2230A6F63F`
  - `0245A5ABF451473AD5AE844D441782F6CC205B5AC23BCBD482525EAFAA9117FD`
  - `025222338AD1333617846CCC0B67F916F3C0D8D1C1F00B1953FFC04FC3FC925A`
  - `02686A34DC9AE6EF50F96293ECD64A1AF55812F7DC6AF67533F93BC5A5C38CC6`
  - `02A696BEA26830205F8CD9282C6390A1F9392CB19FE4E75362D87E77E4F373AF`
  - `02DAC893571A1019CF203AFA24C6754F9A18090B68F743A5694998B09AF4EC04`
  - `02E9CF43024E0CA99022D5C82367118E00EF40C758C74E96638C111C176CC2EB`
  - `02F1BBC8577086280D988A25AE2CFC8096D84F8A6E458C38E4A1780E055BB541`
  - `0300D23FE778621FB6D04414C4D110DD507201317F9FE8D7B89F51F1C5A8B1BC`
  - `03116634D61DE3350DB21317B3C556D752B999ACD29C4FFBEF48C5686E13289D`
  - `0312FD5BB5A2272B798AB79BF7B412671BCA49DD22519F533C09E0D35C25884D`
  - `03AE84BACEB3F5444BAB0C5A017083D4D46CA32CF99F8F103633CB60D001BBBC`
  - `03BD1842D9C4FB06592401F69BA2A47506219898056594F79BC938906AFDB2E2`
  - `0457CD3706B428E17646B0E204D1C6BA412CF31F4F5BD3ADB29141B91911507F`
  - `047739B13F588E14D1844DF450AEC2BAD89828DDF2C36B8E026DE0E11ED29A1C`
  - `04A4E704D2EC28DB53BA13C261C57857C874FA5F3A99DC4B074B6329BC1A9DD2`
  - `04F14E8BA19CBE0855F361FDF90F19669E8A1DCCF4111573EEE75506A35FF48D`
  - `04FFD92A6AAF7AA57B23C4380BA54B8E611082AA051F9866CE52282DB3CD65AC`
  - `0516D97A64776F49058CF0BB4342F4F67AA012A7C6E523227671AD6479F4471E`
  - `052524DDBD8247386BC99E4B85F6261356248639A39EBB5C2050F4BB81FA79E4`
  - `0527CAC9BF33CADF108A12390AB776147CFAF8DA9542EB4DA97085344BD0BDD1`
  - `052F98174347BED0A7906B1674E53C5A48F7D087F3F3BA697584D73EFA26FF4E`
  - `053F5618A9FB4FDF23BDFB63170E218A043A7EE8F814EB532BBDE615CF9AF475`
  - `0553F047A130E108FA15A7629682C00CD05123A00DF1B552DEAE2CF2CE0F4043`
  - `055F704AF1CE7B422E101150C673385773CBF8AD71B6381592E88EEE715BEB4F`
  - `057D88C17AF419D324FE614473BC9A39EFEA0C20860DFC55F65137BD36C1D958`
  - `05837ED11A7B7CCEB4A8F9946665C99B0D741AEFA0BB4B1EA033C356C1EB08DE`
  - `058F0EF68D62845FE2F478F70E54000820C9D8564B2346D0B4F50E61BEA3E8D9`
  - `05A79C63142DA42456A6E831EE8D9F24AE241A2081E3F4D31AFFE99F728EC842`
  - `05AB01B9706FD267F240643E83A27BC263C099C626708A85C72D1858B7B4D905`
  - `05D4CA16BEF14CD2B083F029B4C24728C17F720B062900861B7144C6E51032C3`
  - `062A137EB9EFC5F7835EA4D61317A3C9EC08EDB8294CF5438888C13B821B6C35`
  - `063164761BAFCE47C889B9D3B8899C3CF05E0FC6C19B853CB8A9AF281A371B14`
  - `0636A0B36F48AA519379E9C6CFD51F325E5715EDB220B3A12F114EC07CD6C7EB`
  - `06A8FC199B4DDCB37CA9CBF5878F037387B1FF2C38B9D1D4809F6C25BC20E49C`
- Builder: `update_graph_sequence` k=5, w_cum, shares-not-counts, 22-node universe asserted
- Sequences: apigraph cache → HOOK-first single-label map (exact n_mapped match)

## Step 1 — Two definitions

### 1a. W-selection proxy category assignment

Code path used in W-selection (and here): normalized callee → one label via the same rules as `categorize_soot_callee` in `abrg/androct/categorize.py`:

```73:98:abrg/androct/categorize.py
def categorize_soot_callee(sig: str) -> str | None:
    ...
    exact = HOOK_API_TO_CATEGORY.get(label)
    if exact and exact in _GRAPH_SET:
        return exact
    cats = categorize_callee(class_name, method_name) - DROPPED_CATEGORIES
    cats &= _GRAPH_SET
    if not cats:
        return None
    for pref in _PRIORITY:
        if pref in cats:
            return pref
    return sorted(cats)[0]
```

**One label per event**, not a set. Selection: HOOK exact hit first; else `_PRIORITY` order over `categorize_callee` set; else `sorted(cats)[0]`.

`categorize_callee` itself returns a **set** (`abrg/api_category_map.py:146`), but that set is collapsed before any windowing proxy or AndroCT graph update sees the stream.

### 1b. Self-loops in the canonical AndroCT builder

```69:72:abrg/androct/graph_build.py
        for j in range(i + 1, min(i + k_burst + 1, n)):
            v = stream[j]
            if u == v:
                continue
```

**Same-category pairs within k=5 do NOT create edges** (no self-loops). Arm B `degenerate_snapshots` counts `n_edges == sum(1 for _ in graph.iter_edges())` after this update (`run6_part3.py:137`) — so self-loops are not present and cannot inflate the non-zero count. A mono-category window has **zero edges by construction**.

### 1c. Multi-category events in the builder

AndroCT `update_graph_sequence` takes `Sequence[str]` — one category string per event (`graph_build.py:53-57`). It activates that one node (`graph.nodes[u].act_count += 1`). It does **not** expand a set.

Arm B loads categories via `categorize_soot_callee` into `app.categories: list[str]` then builds windows from that list (`run6_part3.py:129-134`).

### Do 1a and 1c differ?

**No.** Both the proxy and the builder operate on the **same collapsed single-label stream**. The multi-category set from `categorize_callee` is resolved before either sees the event. That difference **cannot** explain the 0.795 vs 0.294 gap.

## Step 2 — Categories per event (|set| before collapse)

On the 100-app sample, `|categorize_callee ∩ GRAPH_UNIVERSE − DROPPED|` per mapped event (plus HOOK hit):

| class | n_events | mean |set| | median | frac |set|=1 | frac=2 | frac≥3 |
|---|---:|---:|---:|---:|---:|---:|
| benign | 97301 | 1 | 1 | 1 | 0 | 0 |
| malware | 98395 | 1 | 1 | 1 | 0 | 0 |

**Most events are already single-category.** The set/label difference is **not** the explanation; Step 3 must (and does) look elsewhere.

## Step 3 — Build W=20

Contiguous disjoint 20-event windows; trailing remainder dropped. Graphs built with `update_graph_sequence`.

| class | n_windows | proxy mono frac | builder single-active frac | true zero-edge (self counted) | true zero-edge (self excluded) |
|---|---:|---:|---:|---:|---:|
| benign | 4844 | 0.8340 | 0.8340 | 0.8340 | 0.8340 |
| malware | 4898 | 0.3691 | 0.3691 | 0.3691 | 0.3691 |

2×2 agreement (proxy mono × builder zero-edge), per class:

**benign**

| | builder zero-edge yes | builder zero-edge no |
|---|---:|---:|
| proxy mono yes | 4040 | 0 |
| proxy mono no | 0 | 804 |

**malware**

| | builder zero-edge yes | builder zero-edge no |
|---|---:|---:|
| proxy mono yes | 1808 | 0 |
| proxy mono no | 0 | 3090 |

- Self-loops observed in any W=20 window: **0** (benign and malware).
- `builder_n_active` always equals proxy distinct count (collapsed stream).
- Fraction of windows where set-union > proxy distinct (benign): 0 — set expansion does not enter the builder.

**Finding:** proxy mono-category ⇔ true zero-edge on this builder (off-diagonal `proxy_mono_and_nonzero` = 0). The proxy is not inventing emptiness the builder does not have.

## Step 4 — Reconcile against Arm B (decisive)

### 4a. N=8 on the same 100 apps

| class | n_windows | true zero-edge frac | proxy mono (nonempty) | size median | p25 | p75 | n empty pads |
|---|---:|---:|---:|---:|---:|---:|---:|
| benign | 400 | 0.2875 | 0.2803 | 21 | 4 | 110.2 | 4 |
| malware | 400 | 0.2800 | 0.2800 | 67 | 38 | 166 | 0 |

- Arm B full-corpus reference (benign): **0.2939** (`run6/part3_armB/comparison.json` → `primary.degenerate_snapshots.benign.frac_zero_edges`).
- This sample N=8 benign zero-edge: **0.2875** — near reference (sampling OK).

### 4b. Zero-edge by window size (pooled N=8 + fixed-W grid) — DECISIVE TABLE

| size bucket | class | n pooled | zero-edge pooled | n N=8 | zero N=8 | n fixed-W | zero fixed-W |
|---|---|---:|---:|---:|---:|---:|---:|
| 1-5 | benign | 113 | 0.6549 | 113 | 0.6549 | 0 | nan |
| 1-5 | malware | 24 | 0.8333 | 24 | 0.8333 | 0 | nan |
| 6-10 | benign | 9770 | 0.8537 | 59 | 0.3729 | 9711 | 0.8567 |
| 6-10 | malware | 9818 | 0.4489 | 0 | nan | 9818 | 0.4489 |
| 11-20 | benign | 11334 | 0.8377 | 24 | 0 | 11310 | 0.8394 |
| 11-20 | malware | 11451 | 0.3868 | 16 | 0.0625 | 11435 | 0.3872 |
| 21-50 | benign | 9569 | 0.8165 | 72 | 0 | 9497 | 0.8227 |
| 21-50 | malware | 9724 | 0.3228 | 120 | 0.3667 | 9604 | 0.3223 |
| 51-100 | benign | 16 | 0.0625 | 16 | 0.0625 | 0 | nan |
| 51-100 | malware | 72 | 0.4444 | 72 | 0.4444 | 0 | nan |
| 100+ | benign | 112 | 0.1250 | 112 | 0.1250 | 0 | nan |
| 100+ | malware | 168 | 0.0893 | 168 | 0.0893 | 0 | nan |

Same exact size spotlight:

| exact size | class | n N=8 | zero N=8 | mono N=8 | n fixed-W | zero fixed-W | mono fixed-W |
|---:|---|---:|---:|---:|---:|---:|---:|
| 10 | benign | 0 | nan | nan | 9711 | 0.8567 | 0.8567 |
| 10 | malware | 0 | nan | nan | 9818 | 0.4489 | 0.4489 |
| 20 | benign | 4 | 0 | 0 | 4844 | 0.8340 | 0.8340 |
| 20 | malware | 6 | 0 | 0 | 4898 | 0.3691 | 0.3691 |

**Interpretation (decisive):** Same-size rates **diverge**.

| bucket (benign) | zero N=8 | zero fixed-W |
|---|---:|---:|
| 6–10 | 0.373 (n=59) | 0.857 (n=9711) |
| 11–20 | 0.000 (n=24) | 0.839 (n=11310) |
| 21–50 | 0.000 (n=72) | 0.823 (n=9497) |

Size alone does **not** put the two constructions on one curve. What differs is **how windows are sampled**:

- **N=8:** exactly 8 windows per app → each app weighs equally. A long mono-category malware/benign trace contributes 8 windows, not thousands.
- **Fixed W:** `floor(n_mapped/W)` windows per app → long mono traces dominate the pool. One 10k-event single-category app contributes ~1000 W=10 windows, all empty.

Arm B’s 0.294 is an **app-balanced** average over mixed sizes (many large, diverse eighths). W-selection’s 0.795 is a **mass-weighted** rate over fixed-size slices. Both numbers can be right; they answer different questions. The proxy is not the gap.

## Step 5 — True zero-edge vs W on the 100-app sample

Built graphs; self-loops excluded (= included, since none exist). Threshold 0.15.

| W | class | n_windows | proxy mono | true zero-edge | clears 0.15? |
|---:|---|---:|---:|---:|---|
| 10 | benign | 9711 | 0.8567 | 0.8567 | False |
| 10 | malware | 9818 | 0.4489 | 0.4489 | False |
| 15 | benign | 6466 | 0.8435 | 0.8435 | False |
| 15 | malware | 6537 | 0.4008 | 0.4008 | False |
| 20 | benign | 4844 | 0.8340 | 0.8340 | False |
| 20 | malware | 4898 | 0.3691 | 0.3691 | False |
| 25 | benign | 3867 | 0.8273 | 0.8273 | False |
| 25 | malware | 3912 | 0.3425 | 0.3425 | False |
| 30 | benign | 3221 | 0.8221 | 0.8221 | False |
| 30 | malware | 3256 | 0.3249 | 0.3249 | False |
| 40 | benign | 2409 | 0.8161 | 0.8161 | False |
| 40 | malware | 2436 | 0.2861 | 0.2861 | False |

(Step 5 was run regardless of Step 3–4; proxy is not inflated, so this is confirmatory for W-selection numbers, not a re-open of the W grid.)

## Verdict

**PROXY_VALID** — 0.795 stands (sample W=10 benign true zero-edge=0.8567; W=20=0.8340); fixed W genuinely empties adjacency; proxy ≡ builder.

### Against PROXY_INFLATED

- Proxy mono and builder zero-edge agree exactly (off-diagonal 0).
- Self-loops are skipped in code and observed count is 0.
- Every mapped event in the sample has `|set|=1` after universe filter — multi-category activation is not occurring on this path.

### Against reading Arm B 0.294 as a rebuttal of fixed-W emptiness

- Sample N=8 benign zero-edge=0.2875 ≈ Arm B 0.2939 (builder path OK).
- Same-size buckets: N=8 ≪ fixed-W zero-edge (e.g. 11–20: 0.00 vs 0.84) — **not a pure size curve**; app-balanced vs mass-weighted pooling.
- No W in {10…40} clears 0.15 true zero-edge for benign on this sample.

### Implication for E0

Fixed-W self-reference on AndroCT will inherit high empty-adjacency rates among **windows**, unless eligibility or weighting is redesigned (e.g. cap windows per app, or require ≥2 active categories). The W-selection floor failure was not a proxy bug.

---

Artifacts: sample app lists and tables in `results/zero_edge_validation.json`.
