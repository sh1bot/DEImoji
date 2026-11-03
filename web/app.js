'use strict';
const $ = (id) => document.getElementById(id);
const samples = [$('clustered'), $('individual')];
let metadata = { commit: 'local' };
let activeFont;
let requestNumber = 0;

function updateText() {
  for (const sample of samples) sample.textContent = $('text').value;
}

function updatePreset() {
  const emoji = $('preset').value === 'flowers' ? '🌻' : '🧟';
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
  const face = new FontFace('DEImojiPreview', `url("fonts/${file}?build=${encodeURIComponent(metadata.commit)}")`);
  try {
    await face.load();
    if (current !== requestNumber) return;
    if (activeFont) document.fonts.delete(activeFont);
    document.fonts.add(face);
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
