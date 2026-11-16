// The before/after sliders: the range input across the picture moves the handle, and
// the before picture is clipped at it (--pos). Mouse, touch and the arrow keys all work,
// as it is a plain range input.
document.querySelectorAll('.compare').forEach((box) => {
  const range = box.querySelector('input[type=range]');
  const set = () => box.style.setProperty('--pos', range.value + '%');
  range.addEventListener('input', set);
  set();
});
