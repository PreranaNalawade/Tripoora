import re

# Read the file
with open('templates/packages.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the entire loadPackages function to use server data directly
old_function_pattern = r'// Load packages from API\s*async function loadPackages\(\) \{.*?\}\s*(?=// Render packages function)'

new_function = '''// Load packages directly from server-rendered data (no API call)
function loadPackages() {
    console.log('Loading packages from server data...');
    if (packagesData && packagesData.length > 0) {
        console.log(`Found ${packagesData.length} packages`);
        renderPackages(packagesData);
    } else {
        console.warn('No packages data available');
        document.getElementById('packagesGrid').innerHTML = `
            <div class="col-12">
                <div class="text-center py-5">
                    <i class="fas fa-box-open fa-3x text-muted mb-3"></i>
                    <h4 class="text-muted">No Packages Available</h4>
                    <p class="text-muted">Check back soon for amazing travel packages!</p>
                </div>
            </div>
        `;
    }
}

'''

content = re.sub(old_function_pattern, new_function, content, flags=re.DOTALL)

# Write back
with open('templates/packages.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Updated packages.html to use server-rendered data only!")
print("⚡ No API calls - instant loading from database")
print("📦 Packages are loaded directly when page renders")
