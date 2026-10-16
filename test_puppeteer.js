const puppeteer = require('puppeteer-core');

(async () => {
    try {
        console.log("Fetching browser websocket URL...");
        const response = await fetch("http://127.0.0.1:44231/json/version");
        const json = await response.json();
        const browserWSEndpoint = json.webSocketDebuggerUrl;
        
        console.log("Connecting to browser...", browserWSEndpoint);
        const browser = await puppeteer.connect({
            browserWSEndpoint,
            defaultViewport: null
        });
        
        console.log("Connected!");
        const pages = await browser.pages();
        console.log("Pages ouvertes:", pages.length);
        
        // Trouver la page Drive
        let drivePage = pages.find(p => p.url().includes('drive.google.com') && p.url().includes('1Edqavh2ORhg5n5R-zZAj8H-RKK8lV-S0'));
        if (!drivePage) {
            console.log("Onglet Drive (Image bot auto) non trouvé, ouverture d'un nouveau...");
            drivePage = await browser.newPage();
            await drivePage.goto('https://drive.google.com/drive/folders/1Edqavh2ORhg5n5R-zZAj8H-RKK8lV-S0', {waitUntil: 'networkidle2'});
        }
        
        console.log("Drive page is ready:", drivePage.url());
        
        await drivePage.bringToFront();
        
        console.log("Waiting for 'Nouveau' button...");
        // Attendre que la page soit prête
        await new Promise(r => setTimeout(r, 3000));
        
        // On va cliquer sur le bouton "Nouveau"
        const newBtn = await drivePage.evaluateHandle(() => {
            return Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('Nouveau') || (b.innerText || '').includes('New') || (b.getAttribute('aria-label') || '').includes('Nouveau'));
        });
        
        if (newBtn) {
            console.log("Clicking Nouveau...");
            await newBtn.click();
            await new Promise(r => setTimeout(r, 1000));
            
            console.log("Waiting for File Chooser...");
            const [fileChooser] = await Promise.all([
                drivePage.waitForFileChooser(),
                drivePage.evaluate(() => {
                    const uploadBtn = Array.from(document.querySelectorAll('[role="menuitem"]')).find(b => (b.innerText || '').includes('Importer un fichier') || (b.innerText || '').includes('File upload'));
                    if (uploadBtn) uploadBtn.click();
                })
            ]);
            
            console.log("Uploading file...");
            await fileChooser.accept(['/root/shein/photo marie/sz2403276962416149/flatlay/description.txt']);
            console.log("File accepted!");
        } else {
            console.log("Button Nouveau not found!");
        }
        
        await browser.disconnect();
    } catch (e) {
        console.error(e);
    }
})();
