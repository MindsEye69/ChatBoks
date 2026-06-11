const root = document.documentElement;
const themeToggle = document.getElementById("themeToggle");
const terminalFocus = document.getElementById("terminalFocus");
const promptInput = document.getElementById("workbenchPrompt");

function setTheme(theme) {
  root.dataset.theme = theme;
  themeToggle.textContent = theme === "dark" ? "Light" : "Dark";
}

themeToggle.addEventListener("click", () => {
  setTheme(root.dataset.theme === "dark" ? "light" : "dark");
});

terminalFocus.addEventListener("click", () => {
  terminalFocus.classList.add("is-focused");
  promptInput.focus();
});

setTheme(root.dataset.theme || "dark");
