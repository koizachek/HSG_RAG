JS_LISTENER = """
function() {
    document.addEventListener('click', function(e) {
        // 1. Use .closest() to find the <a> tag even if user clicks the text/icon inside it
        const target = e.target.closest('a.appointment-btn');

        if (target) {
            // 2. Prevent the link from opening in a new tab/window
            e.preventDefault();

            // 3. Get the URL from the standard href attribute
            const url = target.getAttribute('href');
            const container = document.getElementById('consultation-iframe-container');

            if (container) {
                container.innerHTML = `
                    <div style="margin-top: 20px; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
                        <div style="background: #f9fafb; padding: 10px; font-weight: bold; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between;">
                            <span>Appointment Booking</span>
                            <button onclick="document.getElementById('consultation-iframe-container').innerHTML=''" style="cursor: pointer; color: red;">✕ Close</button>
                        </div>
                        <iframe src="${url}" width="100%" height="600px" frameborder="0"></iframe>
                    </div>
                `;
                container.scrollIntoView({ behavior: 'smooth' });
            }
        }
    });
}
"""

JS_CLEAR = """
function() {
    const el = document.getElementById('consultation-iframe-container');
    if (el) {
        el.innerHTML = '';
    }
}
"""
