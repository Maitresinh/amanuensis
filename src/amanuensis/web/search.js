const state = { books: [], selected: new Set() };
const corpus = document.querySelector("#corpus");
const bookList = document.querySelector("#book-list");
const bookFilter = document.querySelector("#book-filter");
const selectionCount = document.querySelector("#selection-count");
const form = document.querySelector("#search-form");
const results = document.querySelector("#results");
const resultTitle = document.querySelector("#result-title");
const resultMeta = document.querySelector("#result-meta");
const submitButton = form.querySelector("button[type=submit]");

async function loadCatalogue() {
  const response = await fetch("/api/catalogue");
  if (!response.ok) throw new Error("Catalogue indisponible");
  const data = await response.json();
  state.books = data.books;
  for (const item of data.corpora) {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = item;
    corpus.append(option);
  }
  renderBooks();
}

function visibleBooks() {
  const filter = bookFilter.value.trim().toLocaleLowerCase("fr");
  return state.books.filter((book) => {
    const inCorpus = !corpus.value || book.corpus_ids.includes(corpus.value);
    const matches = !filter || book.title.toLocaleLowerCase("fr").includes(filter);
    return inCorpus && matches;
  });
}

function renderBooks() {
  bookList.replaceChildren();
  for (const book of visibleBooks()) {
    const row = document.createElement("label");
    row.className = `book-row${book.status === "indexable" ? "" : " is-unavailable"}`;
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selected.has(book.book_id);
    checkbox.disabled = book.status !== "indexable";
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selected.add(book.book_id);
      else state.selected.delete(book.book_id);
      updateSelectionCount();
    });
    const text = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = book.title;
    const metadata = document.createElement("small");
    metadata.textContent = book.status === "indexable"
      ? `${book.format.toUpperCase()} · ${book.unit_count} section(s)`
      : `${book.status} · ${book.message}`;
    text.append(title, metadata);
    row.append(checkbox, text);
    bookList.append(row);
  }
  updateSelectionCount();
}

function updateSelectionCount() {
  const count = state.selected.size;
  selectionCount.textContent = `${count} livre${count > 1 ? "s" : ""}`;
}

corpus.addEventListener("change", () => {
  state.selected.clear();
  if (corpus.value) {
    for (const book of state.books) {
      if (book.status === "indexable" && book.corpus_ids.includes(corpus.value)) {
        state.selected.add(book.book_id);
      }
    }
  }
  renderBooks();
});
bookFilter.addEventListener("input", renderBooks);
document.querySelector("#toggle-all").addEventListener("click", () => {
  const selectable = visibleBooks().filter((book) => book.status === "indexable");
  const allSelected = selectable.length > 0 && selectable.every((book) => state.selected.has(book.book_id));
  for (const book of selectable) {
    if (allSelected) state.selected.delete(book.book_id);
    else state.selected.add(book.book_id);
  }
  renderBooks();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selected.size) {
    showError("Selectionnez au moins un livre indexable.");
    return;
  }
  submitButton.disabled = true;
  resultTitle.textContent = "Recherche en cours";
  resultMeta.textContent = "";
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: document.querySelector("#query").value,
        corpus_id: corpus.value || null,
        book_ids: [...state.selected],
        order: form.elements.order.value,
        limit: 30,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Recherche impossible");
    renderResults(data);
  } catch (error) {
    showError(error.message);
  } finally {
    submitButton.disabled = false;
  }
});

function renderResults(data) {
  results.replaceChildren();
  resultTitle.textContent = `${data.count} extrait${data.count > 1 ? "s" : ""}`;
  resultMeta.textContent = `${data.scope.book_ids.length} livre(s) consult\u00e9(s)`;
  if (!data.excerpts.length) {
    results.innerHTML = '<div class="empty-state"><strong>Aucun passage trouve.</strong><p>Essayez une formulation plus concrete ou un corpus plus large.</p></div>';
    return;
  }
  const template = document.querySelector("#excerpt-template");
  for (const excerpt of data.excerpts) {
    const node = template.content.cloneNode(true);
    node.querySelector(".excerpt-book").textContent = excerpt.book_title;
    node.querySelector(".excerpt-location").textContent = excerpt.unit_label;
    node.querySelector(".excerpt-score").textContent = `score ${excerpt.score.toFixed(3)}`;
    node.querySelector("blockquote").textContent = excerpt.text;
    node.querySelector(".excerpt-offsets").textContent = `caract\u00e8res ${excerpt.start}-${excerpt.end}`;
    node.querySelector(".excerpt-channels").textContent = excerpt.channels.join(" + ");
    results.append(node);
  }
}

function showError(message) {
  resultTitle.textContent = "Recherche interrompue";
  resultMeta.textContent = "";
  results.innerHTML = `<div class="empty-state error"><strong></strong></div>`;
  results.querySelector("strong").textContent = message;
}

loadCatalogue().catch((error) => showError(error.message));
