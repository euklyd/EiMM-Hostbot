import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import "./style.css";

// Apply saved theme before mount to avoid flash of wrong theme
const savedTheme = localStorage.getItem("theme") ?? "discord";
document.documentElement.setAttribute("data-theme", savedTheme);

const app = createApp(App);

app.use(createPinia());
app.use(router);

app.mount("#app");
