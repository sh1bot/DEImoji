'use strict';
const $ = (id) => document.getElementById(id);
const samples = [$('clustered'), $('individual')];
let metadata = { commit: 'local' };
let activeFont;
let requestNumber = 0;
const graphemes = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
const isEmoji = /\p{Extended_Pictographic}|\p{Regional_Indicator}|\u20e3/u;
const invisibleNames = new Map([
  [0x00A0, 'NBSP'], [0x00AD, 'SOFT HYPHEN'],
  [0x200B, 'ZERO WIDTH SPACE'], [0x200C, 'ZWNJ'], [0x200D, 'ZWJ'],
  [0x2060, 'WORD JOINER'], [0xFE0E, 'VS15 (text)'], [0xFE0F, 'VS16 (emoji)'],
  [0xE007F, 'CANCEL TAG'],
]);

function describeCodepoints(text) {
  const tokens = [];
  let ascii = '';
  const flush = () => {
    if (ascii) tokens.push(JSON.stringify(ascii));
    ascii = '';
  };
  for (const character of text) {
    const cp = character.codePointAt(0);
    if (cp < 0x80) ascii += character;
    else {
      flush();
      const hex = `U+${cp.toString(16).toUpperCase().padStart(4, '0')}`;
      let name = invisibleNames.get(cp);
      if (!name && cp >= 0xFE00 && cp <= 0xFE0F) name = `VS${cp - 0xFE00 + 1}`;
      if (cp >= 0xE0020 && cp <= 0xE007E) name = `TAG ${JSON.stringify(String.fromCharCode(cp - 0xE0000))}`;
      if (cp >= 0xE0100 && cp <= 0xE01EF) name = `VS${cp - 0xE0100 + 17}`;
      if (!name && /\p{Cf}|\p{Cc}/u.test(character)) name = 'FORMAT CONTROL';
      tokens.push(name ? `${hex} (${name})` : `${hex} (${character})`);
    }
  }
  flush();
  return tokens.join(' · ');
}

function updateText() {
  const text = $('text').value;
  $('codepoints').textContent = describeCodepoints(text) || '(empty input)';
  const runs = [];
  for (const { segment } of graphemes.segment(text)) {
    const emoji = isEmoji.test(segment);
    const last = runs[runs.length - 1];
    if (last && last.emoji === emoji) last.text += segment;
    else runs.push({ emoji, text: segment });
  }
  for (const sample of samples) {
    const content = document.createDocumentFragment();
    for (const run of runs) {
      if (run.emoji) {
        const span = document.createElement('span');
        span.className = 'emoji-run';
        span.textContent = run.text;
        content.append(span);
      } else content.append(document.createTextNode(run.text));
    }
    sample.replaceChildren(content);
  }
}

function updatePreset() {
  const emoji = { flowers: '🌻', zombies: '🧟', runners: '🏃', poop: '💩' }[$('preset').value];
  $('text').value = emoji.repeat(Number($('count').value));
  $('count-value').textContent = $('count').value;
  updateText();
}

async function loadFont() {
  const current = ++requestNumber;
  const file = $('format').value === 'colr' ? 'DEImoji-COLRv1.woff2' : 'DEImoji-CBDT.ttf';
  $('status').className = '';
  $('status').textContent = 'Loading the built font…';
  samples.forEach((sample) => sample.classList.add('waiting'));
  const family = `DEImojiPreview-${current}`;
  const face = new FontFace(family, `url("fonts/${file}?build=${encodeURIComponent(metadata.commit)}")`);
  try {
    await face.load();
    if (current !== requestNumber) return;
    if (activeFont) document.fonts.delete(activeFont);
    document.fonts.add(face);
    document.documentElement.style.setProperty('--emoji-font', family);
    activeFont = face;
    samples.forEach((sample) => sample.classList.remove('waiting'));
    $('status').textContent = 'Built font loaded. Both samples use this exact font.';
  } catch (error) {
    if (current !== requestNumber) return;
    $('status').className = 'error';
    $('status').textContent = 'Could not load this font. Try the other format or download the build. Samples are hidden to avoid showing system emoji as the result.';
  }
}

async function initialize() {
  updatePreset();
  $('preset').addEventListener('change', updatePreset);
  $('count').addEventListener('input', updatePreset);
  $('text').addEventListener('input', updateText);
  $('size').addEventListener('input', () => {
    const size = $('size').value;
    document.documentElement.style.setProperty('--size', `${size}px`);
    $('size-value').textContent = `${size} px`;
  });
  $('format').addEventListener('change', loadFont);
  try {
    const response = await fetch('build.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('Build metadata unavailable');
    metadata = await response.json();
    const link = document.createElement('a');
    link.href = `https://github.com/${metadata.repository}/commit/${metadata.commit}`;
    link.textContent = metadata.commit.slice(0, 7);
    $('build').replaceChildren('Build ', link, ` · ${new Date(metadata.built_at).toLocaleString()}`);
    document.querySelectorAll('nav a').forEach((a) => {
      a.href += `?build=${encodeURIComponent(metadata.commit)}`;
    });
  } catch (error) {
    $('build').textContent = 'Local preview · build information unavailable';
  }
  await loadFont();
}

initialize();
