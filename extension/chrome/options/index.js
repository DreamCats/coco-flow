import { createOptionsActions } from "./actions.js";
import { getOptionsElements } from "./elements.js";
import { createOptionsState } from "./state.js";

const state = createOptionsState();
const elements = getOptionsElements();
const actions = createOptionsActions(state, elements);

function bindEvents() {
  elements.retry.addEventListener("click", () => {
    void actions.refreshGateway();
  });
  elements.refresh.addEventListener("click", () => {
    void actions.loadRemotes();
  });
  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    void actions.createRemote();
  });
}

async function boot() {
  bindEvents();
  await actions.boot();
}

void boot();
