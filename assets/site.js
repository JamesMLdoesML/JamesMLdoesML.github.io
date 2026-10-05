const languageButtons = document.querySelectorAll(".language-switch button");
const translatedLabels = document.querySelectorAll("[data-english][data-singlish]");
const themeToggle = document.querySelector(".theme-toggle");

function setLanguage(language) {
  translatedLabels.forEach((element) => {
    element.textContent = element.dataset[language];
  });

  languageButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.language === language));
  });

  document.documentElement.lang = language === "singlish" ? "en-SG" : "en";
  try { localStorage.setItem("language", language); } catch {}
}

languageButtons.forEach((button) => {
  button.addEventListener("click", () => setLanguage(button.dataset.language));
});

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  themeToggle.checked = theme === "dark";
  try { localStorage.setItem("theme", theme); } catch {}
}

if (themeToggle) {
  themeToggle.checked = document.documentElement.dataset.theme === "dark";
  themeToggle.addEventListener("change", () => setTheme(themeToggle.checked ? "dark" : "light"));
}

let savedLanguage = "english";
try { savedLanguage = localStorage.getItem("language") || "english"; } catch {}
setLanguage(savedLanguage === "singlish" ? "singlish" : "english");
