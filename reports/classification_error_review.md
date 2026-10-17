# Category and factuality review ? 2026-10-10

Reviewed all **15 category mismatches** from the four-frame constrained run. Strict accuracy remains **8/23 (34.8%)**; no labels or scores were changed. These are assistant judgments for annotation review, not independent human adjudication.

**7 cases have a clearly unsupported or missed topic/purpose; 8 require taxonomy or source-provenance adjudication.** Ambiguity does not make a prediction correct. Ten of the 15 mismatches use `Entertainment & Shows` (10/23 predictions overall), including clips whose own generated summaries already identify dancing, cars or skincare.

Evidence comprises full supplied transcripts, reference summaries and four independently sampled frames per mismatch (5%, 35%, 65%, 95%). These are not exact inference frames or full-video playback. Audio was not independently retranscribed. Only errors were reviewed, so this is not an overall factuality estimate.

## Per-case findings

| Video ID | Reference ? prediction | Provisional finding |
|---|---|---|
| 7226368631268019482 | Relationship ? Music, Singing, & Dancing | taxonomy ambiguity: Relationship or Music, Singing, & Dancing; requires a theme-versus-format rule |
| 7299582823940312350 | Drama ? Entertainment & Shows | taxonomy ambiguity: Drama or Entertainment & Shows; genre boundary unresolved |
| 7299771215755906312 | Music, Singing, & Dancing ? Entertainment & Shows | clear model topic error: Music, Singing, & Dancing |
| 7311332422077975840 | Comedy ? Entertainment & Shows | taxonomy ambiguity: Comedy preferred if comic sketches take priority over Entertainment & Shows |
| 7317764806767922475 | Family ? Entertainment & Shows | taxonomy ambiguity: Family preferred if parent-child context takes priority; Fitness & Health and Daily Life also plausible |
| 7323547689201765664 | Autos & Vehicles ? Comedy | clear model topic error: Autos & Vehicles |
| 7328941581862473006 | Gaming ? Entertainment & Shows | taxonomy ambiguity: Gaming only after verifying source; Entertainment & Shows or Film & Animation remains plausible |
| 7358352976639184146 | Travel & Events ? Science & Technology | clear model topic error: Travel & Events is plausible; exact boundary with Autos & Vehicles or News needs policy |
| 7364542326959574314 | Daily Life ? Entertainment & Shows | taxonomy ambiguity: Daily Life or Relationship; Beauty Care is secondary to the reaction |
| 7367380929913900320 | Outfit, Style, & Howto ? Entertainment & Shows | clear model topic error: Outfit, Style, & Howto |
| 7376360928851299590 | Beauty Care ? Entertainment & Shows | clear model topic error: Beauty Care |
| 7395616033127648554 | Fitness & Health ? Entertainment & Shows | clear model topic error: Fitness & Health |
| 7396760829498002720 | People & Blogs ? Entertainment & Shows | taxonomy ambiguity: People & Blogs preferred under a personal-monologue rule |
| 7397523950391086369 | Entertainment & Shows ? Film & Animation | taxonomy ambiguity: Film & Animation is defensible; original Entertainment & Shows needs adjudication |
| 7408631372044111135 | Nonprofits & Activism ? Pets & Animals | clear model topic error: Nonprofits & Activism under an explicit fundraising-appeal rule |

## Summary and data issues

- **7226368631268019482**: The generated summary captures the song-recommendation title but ends inside a quotation. The transcript only introduces the recommendation.

- **7299582823940312350**: Reference calls the handheld object a remote; prediction calls it a gun. Its silhouette looks gun-shaped in the review frame, but identity is unresolved. Do not score this as a proven model hallucination or silently correct the reference.

- **7299771215755906312**: The core dance description is supported. Four review frames cannot verify every claimed jump or the exact ending.

- **7311332422077975840**: Transcript identifies the police captain as the boy's dad and ends with the woman being arrested for attempted robbery. Reference instead describes a grandson, an apology and a resolved misunderstanding. Generated summary misses the plot and ends mid-sentence.

- **7317764806767922475**: Review frames show separate bath containers; the summary describes holding the child and helping them into a large container, which these frames do not establish. Transcript includes pregnancy/belly and winter-bathing context.

- **7323547689201765664**: Summary treats GTC4 Lusso as the second choice, although the speaker subsequently chooses Roma; it ends before completing the list. Reference is also incomplete, omitting LaFerrari and containing vehicle-name transcription problems.

- **7328941581862473006**: Generated summary overemphasizes HIGH text and altitude. It does not resolve whether this is game footage, a film edit or another source. Reference Gaming label requires provenance review.

- **7358352976639184146**: Model adds a driver's black shirt, a white car and a final sky view not supported by the sampled windshield footage. Supplied transcript is incoherent and unrelated to the visible driving scene; mark it suspect rather than treating it as trusted evidence.

- **7364542326959574314**: Generated summary captures excitement but omits the nail/photo/relationship context carried by the overlay. Background-song transcript does not explain the central scene.

- **7367380929913900320**: Model changes the encouragement into wear sweaters instead, reversing the message. This is a supported OCR/meaning error, not merely a category-boundary disagreement.

- **7376360928851299590**: Summary flattens a critical discussion of expectations into benefits and adds an ending wardrobe change not established by sampled frames. This review describes the speaker's claims and does not validate skincare efficacy. Language handling is a hypothesis, not a proven root cause.

- **7395616033127648554**: Model describes clothing, bag and tattoo while omitting the advertising claim. Black dress versus scrubs is uncertain from these views. Health claims are advertising content, not verified medical facts.

- **7396760829498002720**: Model inverts the intent into reasons not to buy or keep books. Transcript instead says physical editions are bought after reading and retained as trophies. This is a clear summary negation/intent error despite category ambiguity.

- **7397523950391086369**: Model repeats the same green-apple/purple-character sequence many times. Reference-category disagreement alone should not be used as proof of a semantic model failure.

- **7408631372044111135**: Generated summary repeats petting/hand details and misses the donation plea and medication-loss context. Pets & Animals describes the subject but misses the communicated purpose.

## Targeted improvement

Keep the four-frame development reference and constrained category decoder. The next hypothesis is a category prompt that defines boundaries and uses the central topic/purpose, transcript and visible text, with the generated summary as supporting evidence. Dancing, cars and skincare should select specific labels; an explicit rescue fundraiser should prioritize its appeal over its animal subject. This has not been implemented or measured by this review.

Before evaluating that hypothesis, adjudicate theme versus format (Relationship/Music), genre versus format (Drama/Comedy/Entertainment), animation versus generic Entertainment, and personal diaries versus generic Entertainment. Verify the fighter-jet clip's provenance. Resolve reference-summary conflicts for the police sketch, car list and handheld object. Version any agreed annotation changes and report results against both original and revised labels; do not retroactively improve this run's accuracy.

Summary evaluation also needs factual checks for negation, OCR, omitted intent and repetition; a high embedding-similarity score does not resolve these defects. Background music and incoherent transcripts should not override reliable visible text. No numerical production gate can be justified by these 23 examples.

## Reserved evaluation subset

Reserved **57 videos across 21 categories**, up to three per category, excluding **24 IDs** found in local development/smoke reports, configs and output journals (including configured or failed attempts). Selection is deterministic and records source hashes. No inference was run on the reserved videos and their content was not reviewed for this reservation.

Education, Fitness & Health, and Nonprofits & Activism have only one remaining example each. Drama and Science & Technology have no remaining eligible example after development exclusion; Lipsync and Society had no eligible examples initially. Collect new examples for these gaps. The set is neither population representative nor a production acceptance set: independent annotation and an audit of historical research/training exposure remain necessary. Local disjointness does not establish global holdout status.

The reservation is write-once: changing exposure evidence requires a reviewed new version instead of silently replacing examples. See [reserved-eval-v1.json](../data/manifests/reserved-eval-v1.json) and `scripts/build_reserved_evaluation.py`.

Detailed evidence, source checksums, original summaries, provisional verdicts and contact-sheet paths are in [classification_error_review.json](classification_error_review.json); the [CSV](classification_error_review.csv) is a compact review sheet. Contact sheets are local ignored artifacts under `data/outputs/classification-review/frames/`.
