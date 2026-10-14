# Verify the benchmark claims (human step)

`eval/claims_draft.jsonl` holds 40 **candidate** claims (20 TRUE, 20 FALSE) written by Claude Code.
The benchmark is only worth something if every label is correct, so a person must check each one.

1. For each row below, open the evidence link and confirm the label from what the source says.
2. If a label is wrong, fix it in `eval/claims_draft.jsonl`. If a claim is ambiguous (could fairly be
   MISLEADING or depends on definitions), replace it with a clearer claim and a real evidence link,
   keeping 20 TRUE and 20 FALSE.
3. Tick the **Confirmed** column here as you go.
4. When all 40 are confirmed, save the file as `eval/claims.jsonl`:
   `cp eval/claims_draft.jsonl eval/claims.jsonl`
5. Then run the benchmark: `.venv/bin/python scripts/run_eval.py` (needs the Token Factory and Tavily keys in `.env`).

`scripts/run_eval.py` refuses to run until `eval/claims.jsonl` exists.

| ID | Claim | Label | Evidence | Confirmed |
|---|---|---|---|---|
| c01 | Light from the Sun takes about 8 minutes to reach Earth. | TRUE | [link](https://en.wikipedia.org/wiki/Sunlight) | [ ] |
| c02 | The human heart has four chambers. | TRUE | [link](https://en.wikipedia.org/wiki/Heart) | [ ] |
| c03 | The Pacific Ocean is the largest ocean on Earth. | TRUE | [link](https://en.wikipedia.org/wiki/Pacific_Ocean) | [ ] |
| c04 | Mount Kilimanjaro is the highest mountain in Africa. | TRUE | [link](https://en.wikipedia.org/wiki/Mount_Kilimanjaro) | [ ] |
| c05 | The Berlin Wall fell in 1989. | TRUE | [link](https://en.wikipedia.org/wiki/Berlin_Wall) | [ ] |
| c06 | Penicillin was discovered by Alexander Fleming in 1928. | TRUE | [link](https://en.wikipedia.org/wiki/Penicillin) | [ ] |
| c07 | Diamonds are made of carbon. | TRUE | [link](https://en.wikipedia.org/wiki/Diamond) | [ ] |
| c08 | The first iPhone was released in 2007. | TRUE | [link](https://en.wikipedia.org/wiki/IPhone_(1st_generation)) | [ ] |
| c09 | Canberra is the capital city of Australia. | TRUE | [link](https://en.wikipedia.org/wiki/Canberra) | [ ] |
| c10 | Antibiotics do not work against viral infections such as the common cold. | TRUE | [link](https://en.wikipedia.org/wiki/Antibiotic) | [ ] |
| c11 | Jupiter is the largest planet in the Solar System. | TRUE | [link](https://en.wikipedia.org/wiki/Jupiter) | [ ] |
| c12 | Apollo 11 landed the first humans on the Moon in July 1969. | TRUE | [link](https://en.wikipedia.org/wiki/Apollo_11) | [ ] |
| c13 | The Amazon River flows into the Atlantic Ocean. | TRUE | [link](https://en.wikipedia.org/wiki/Amazon_River) | [ ] |
| c14 | Humans normally have 23 pairs of chromosomes. | TRUE | [link](https://medlineplus.gov/genetics/understanding/basics/howmanychromosomes/) | [ ] |
| c15 | The World Wide Web was invented by Tim Berners-Lee. | TRUE | [link](https://en.wikipedia.org/wiki/Tim_Berners-Lee) | [ ] |
| c16 | A severe lack of vitamin C causes scurvy. | TRUE | [link](https://en.wikipedia.org/wiki/Scurvy) | [ ] |
| c17 | The Great Pyramid of Giza was built during Egypt's Fourth Dynasty. | TRUE | [link](https://en.wikipedia.org/wiki/Great_Pyramid_of_Giza) | [ ] |
| c18 | Sound cannot travel through a vacuum. | TRUE | [link](https://en.wikipedia.org/wiki/Sound) | [ ] |
| c19 | The Sahara is the largest hot desert in the world. | TRUE | [link](https://en.wikipedia.org/wiki/Sahara) | [ ] |
| c20 | The Python programming language was first released in 1991. | TRUE | [link](https://en.wikipedia.org/wiki/Python_(programming_language)) | [ ] |
| c21 | Vaccines cause autism. | FALSE | [link](https://en.wikipedia.org/wiki/Vaccines_and_autism) | [ ] |
| c22 | The Moon produces its own light. | FALSE | [link](https://en.wikipedia.org/wiki/Moonlight) | [ ] |
| c23 | Sydney is the capital city of Australia. | FALSE | [link](https://en.wikipedia.org/wiki/Canberra) | [ ] |
| c24 | Thomas Edison invented the telephone. | FALSE | [link](https://en.wikipedia.org/wiki/Invention_of_the_telephone) | [ ] |
| c25 | The Eiffel Tower was completed in 1925. | FALSE | [link](https://en.wikipedia.org/wiki/Eiffel_Tower) | [ ] |
| c26 | The Nile River flows into the Red Sea. | FALSE | [link](https://en.wikipedia.org/wiki/Nile) | [ ] |
| c27 | Antibiotics are an effective treatment for the flu virus. | FALSE | [link](https://en.wikipedia.org/wiki/Influenza) | [ ] |
| c28 | The Titanic sank in 1920. | FALSE | [link](https://en.wikipedia.org/wiki/Titanic) | [ ] |
| c29 | Venus is the closest planet to the Sun. | FALSE | [link](https://en.wikipedia.org/wiki/Mercury_(planet)) | [ ] |
| c30 | Microsoft was founded by Steve Jobs. | FALSE | [link](https://en.wikipedia.org/wiki/Microsoft) | [ ] |
| c31 | Blood inside human veins is blue. | FALSE | [link](https://en.wikipedia.org/wiki/Blood) | [ ] |
| c32 | Mount Everest is in the Andes mountain range. | FALSE | [link](https://en.wikipedia.org/wiki/Mount_Everest) | [ ] |
| c33 | Cracking your knuckles causes arthritis. | FALSE | [link](https://en.wikipedia.org/wiki/Cracking_joints) | [ ] |
| c34 | Albert Einstein failed mathematics at school. | FALSE | [link](https://en.wikipedia.org/wiki/Albert_Einstein) | [ ] |
| c35 | The Great Fire of London happened in 1766. | FALSE | [link](https://en.wikipedia.org/wiki/Great_Fire_of_London) | [ ] |
| c36 | Diamonds form from compressed coal. | FALSE | [link](https://en.wikipedia.org/wiki/Diamond) | [ ] |
| c37 | Glass is a slow-flowing liquid, which is why old windows are thicker at the bottom. | FALSE | [link](https://en.wikipedia.org/wiki/Glass) | [ ] |
| c38 | The Sun orbits the Earth. | FALSE | [link](https://en.wikipedia.org/wiki/Heliocentrism) | [ ] |
| c39 | Viking warriors wore horned helmets in battle. | FALSE | [link](https://en.wikipedia.org/wiki/Horned_helmet) | [ ] |
| c40 | Bats are blind. | FALSE | [link](https://en.wikipedia.org/wiki/Bat) | [ ] |
