document.addEventListener('click', e => {
  if (!e.target.closest('.copy-btn')) return;
  const btn = e.target.closest('.copy-btn');
  const cmd = btn.dataset.cmd;
  navigator.clipboard.writeText(cmd).then(() => {
    btn.title = 'Copied!';
    setTimeout(() => btn.removeAttribute('title'), 1500);
  }).catch(() => alert('Copy failed'));
});

// copy.js – attached at the bottom of the page
document.addEventListener('click', e => {
  const btn = e.target.closest('.copy-btn');
  if (!btn) return;

  const cmd = btn.dataset.cmd;
  navigator.clipboard.writeText(cmd).then(() => {
    btn.title = 'Copied!';
    setTimeout(() => btn.removeAttribute('title'), 1500);
  }).catch(() => {
    // fallback for very old browsers
    const textarea = document.createElement('textarea');
    textarea.value = cmd;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    btn.title = 'Copied!';
    setTimeout(() => btn.removeAttribute('title'), 1500);
  });
});
