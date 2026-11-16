// A screenshot clicked opens enlarged over the page, not as the raw image: Esc, a click or
// the close button shuts it; the arrows (and the left and right keys) step through the
// pictures of its group (a gallery, or a change's before/after).
(() => {
  const box = document.createElement('div');
  box.className = 'lightbox';
  box.hidden = true;
  box.innerHTML = '<button class="lb-close" aria-label="Close">&times;</button>' +
    '<button class="lb-prev" aria-label="Previous">&lsaquo;</button>' +
    '<figure><img alt=""><figcaption></figcaption></figure>' +
    '<button class="lb-next" aria-label="Next">&rsaquo;</button>';
  document.body.append(box);
  const img = box.querySelector('img'), cap = box.querySelector('figcaption');
  let group = [], at = 0;

  const show = (i) => {
    at = (i + group.length) % group.length;
    const a = group[at], pic = a.querySelector('img');
    img.src = a.getAttribute('href');
    img.alt = pic.alt;
    img.classList.toggle('pixel', !!a.closest('.classic, .shots'));
    cap.textContent = a.closest('figure')?.querySelector('figcaption')?.textContent || pic.alt;
    box.querySelector('.lb-prev').hidden = box.querySelector('.lb-next').hidden = group.length < 2;
  };
  const close = () => { box.hidden = true; document.body.classList.remove('lb-open'); };

  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href^="img/"]');
    if (!a || !a.querySelector('img') || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    const scope = a.closest('.gallery, .shots') || a;
    group = [...scope.querySelectorAll('a[href^="img/"]')].filter((x) => x.querySelector('img'));
    show(group.indexOf(a));
    box.hidden = false;
    document.body.classList.add('lb-open');
  });
  box.addEventListener('click', (e) => {
    if (e.target.closest('.lb-prev')) show(at - 1);
    else if (e.target.closest('.lb-next')) show(at + 1);
    else if (e.target !== img) close();
  });
  document.addEventListener('keydown', (e) => {
    if (box.hidden) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft' && group.length > 1) show(at - 1);
    else if (e.key === 'ArrowRight' && group.length > 1) show(at + 1);
  });
})();
