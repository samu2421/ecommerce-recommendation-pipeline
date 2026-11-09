const apiUrl = 'http://localhost:5001';  // Change this if needed based on your Flask server

function trainModel() {
    const messageDiv = document.getElementById('message');
    messageDiv.textContent = 'Training the model...';

    fetch(`${apiUrl}/train`, {
        method: 'POST',
    })
    .then(response => response.json())
    .then(data => {
        if (data.message) {
            messageDiv.textContent = 'Model trained successfully!';
        } else {
            messageDiv.textContent = `Error: ${data.error}`;
        }
    })
    .catch(error => {
        messageDiv.textContent = `Error: ${error}`;
    });
}

function getRecommendations() {
    const customerId = document.getElementById('customer-id').value;
    const numRecommendations = document.getElementById('num-recommendations').value;
    const recommendationsList = document.getElementById('recommendations-list');
    const messageDiv = document.getElementById('message');
    recommendationsList.innerHTML = '';  // Clear previous recommendations
    messageDiv.textContent = 'Fetching recommendations...';

    if (!customerId) {
        messageDiv.textContent = 'Please enter a customer ID.';
        return;
    }

    fetch(`${apiUrl}/recommendations/${encodeURIComponent(customerId)}?n=${encodeURIComponent(numRecommendations)}`, {
        method: 'GET',
    })
    .then(response => response.json())
    .then(data => {
        recommendationsList.innerHTML = ''; // Clear previous recommendations
        if (Array.isArray(data) && data.length > 0) {
            data.forEach(item => {
                const productCard = document.createElement('div');
                productCard.classList.add('col');

                // Build the Bootstrap card with DOM APIs; API text is set via textContent
                const card = document.createElement('div');
                card.className = 'card recommendation-card';

                const body = document.createElement('div');
                body.className = 'card-body recommendation-card-body';

                const title = document.createElement('h5');
                title.className = 'card-title recommendation-title';
                title.textContent = item.description || '(no description)';

                const stockCode = document.createElement('p');
                stockCode.className = 'recommendation-score';
                stockCode.textContent = `Stock Code: ${item.stock_code}`;

                const score = document.createElement('p');
                score.className = 'recommendation-score';
                score.textContent = `Score: ${Number(item.score).toFixed(2)}`;

                body.append(title, stockCode, score);
                card.appendChild(body);
                productCard.appendChild(card);

                // Append the card to the recommendations list
                recommendationsList.appendChild(productCard);
            });
            messageDiv.textContent = 'Recommendations fetched successfully!';
        } else if (data && data.error) {
            messageDiv.textContent = `Error: ${data.error}`;
        } else {
            messageDiv.textContent = 'No recommendations found.';
        }
    })
    .catch(error => {
        messageDiv.textContent = `Error: ${error}`;
    });
}