const searchInput = document.getElementById("search-input");
const suggestionsContainer = document.getElementById("search-suggestions");

// Debounce helper
function debounce(fn, delay) {
    let timeoutId;
    return (...args) => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn(...args), delay);
    };
}

const fetchSuggestions = async (query) => {
    if (!query) {
        suggestionsContainer.innerHTML = "";
        return;
    }

    try {
        const response = await fetch(`/api/search-suggestions?query=${encodeURIComponent(query)}`);
        const data = await response.json();

        suggestionsContainer.innerHTML = "";

        data.topics.forEach(topic => {
            const link = document.createElement("a");
            link.href = `/topic/${topic.id}`;
            link.classList.add("suggestion-item", "suggestion-item--topic");
            link.textContent = topic.name;
            suggestionsContainer.appendChild(link);
        });

        data.posts.forEach(post => {
            const link = document.createElement("a");
            link.href = `/post/${post.post_id}`;
            link.classList.add("suggestion-item", "suggestion-item--post");
            link.textContent = post.caption;
            suggestionsContainer.appendChild(link);
        });

    } catch (err) {
        console.error("Error fetching suggestions:", err);
    }
};

searchInput.addEventListener("input", debounce((e) => {
    fetchSuggestions(e.target.value.trim());
}, 150));
