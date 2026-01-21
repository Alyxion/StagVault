/**
 * Unit tests for HTML stripping functionality.
 * Ensures no API source ever returns HTML tags in titles.
 * Run with: node tests/test_strip_html.js
 */

// Copy of stripHtml function from app.js for testing
function stripHtml(text) {
    if (!text || typeof text !== 'string') return text;
    // Check if text contains HTML tags
    if (!text.includes('<') || !text.includes('>')) return text;
    // Simple HTML tag removal using regex (no DOM available in Node)
    return text.replace(/<[^>]*>/g, '').trim();
}

// Test cases for stripHtml function
const stripHtmlTests = [
    {
        name: 'Returns null for null input',
        input: null,
        expected: null
    },
    {
        name: 'Returns undefined for undefined input',
        input: undefined,
        expected: undefined
    },
    {
        name: 'Returns empty string for empty string',
        input: '',
        expected: ''
    },
    {
        name: 'Returns plain text unchanged',
        input: 'Hello World',
        expected: 'Hello World'
    },
    {
        name: 'Strips simple HTML tag',
        input: '<b>Bold</b>',
        expected: 'Bold'
    },
    {
        name: 'Strips nested HTML tags',
        input: '<div><span>Nested</span></div>',
        expected: 'Nested'
    },
    {
        name: 'Strips div with class (Wikimedia ObjectName case)',
        input: '<div class="fn">File name</div>',
        expected: 'File name'
    },
    {
        name: 'Strips complex Wikimedia-style HTML',
        input: '<div class="fn"> <div style="font-weight:bold;display:inline;">Woman on Beach</div></div>',
        expected: 'Woman on Beach'
    },
    {
        name: 'Strips HTML with attributes',
        input: '<a href="https://example.com" target="_blank">Link Text</a>',
        expected: 'Link Text'
    },
    {
        name: 'Strips self-closing tags',
        input: 'Before<br/>After',
        expected: 'BeforeAfter'
    },
    {
        name: 'Strips script tags',
        input: 'Safe<script>alert("xss")</script>Text',
        expected: 'Safealert("xss")Text'
    },
    {
        name: 'Handles multiple HTML blocks',
        input: '<p>First</p><p>Second</p>',
        expected: 'FirstSecond'
    },
    {
        name: 'Preserves angle brackets in non-HTML contexts',
        input: '5 > 3 and 2 < 4',
        expected: '5 > 3 and 2 < 4'
    },
    {
        name: 'Returns number unchanged',
        input: 123,
        expected: 123
    },
    {
        name: 'Returns array unchanged',
        input: ['a', 'b'],
        expected: ['a', 'b']
    }
];

// Test cases simulating API responses that might contain HTML
const apiResponseTests = [
    {
        name: 'Wikimedia Commons ObjectName with HTML wrapper',
        source: 'wikimedia',
        rawResponse: {
            ObjectName: { value: '<div class="fn">Beautiful sunset over mountains</div>' }
        },
        field: 'ObjectName',
        expectedClean: 'Beautiful sunset over mountains'
    },
    {
        name: 'Wikimedia ImageDescription with nested HTML',
        source: 'wikimedia',
        rawResponse: {
            ImageDescription: { value: '<div>A <b>beautiful</b> <i>sunset</i></div>' }
        },
        field: 'ImageDescription',
        expectedClean: 'A beautiful sunset'
    },
    {
        name: 'Wikimedia Artist with link',
        source: 'wikimedia',
        rawResponse: {
            Artist: { value: '<a href="/wiki/User:Photographer">John Doe</a>' }
        },
        field: 'Artist',
        expectedClean: 'John Doe'
    },
    {
        name: 'Wikimedia LicenseShortName',
        source: 'wikimedia',
        rawResponse: {
            LicenseShortName: { value: '<a href="/wiki/CC_BY_4.0">CC BY 4.0</a>' }
        },
        field: 'LicenseShortName',
        expectedClean: 'CC BY 4.0'
    },
    {
        name: 'Pexels alt text (should be plain)',
        source: 'pexels',
        rawResponse: {
            alt: 'Woman in red dress'
        },
        field: 'alt',
        expectedClean: 'Woman in red dress'
    },
    {
        name: 'Pixabay tags (should be plain)',
        source: 'pixabay',
        rawResponse: {
            tags: 'nature, landscape, mountains'
        },
        field: 'tags',
        expectedClean: 'nature, landscape, mountains'
    },
    {
        name: 'Unsplash description (should be plain)',
        source: 'unsplash',
        rawResponse: {
            description: 'Aerial view of coastline'
        },
        field: 'description',
        expectedClean: 'Aerial view of coastline'
    }
];

// Helper to check if text contains HTML tags
function containsHtmlTags(text) {
    if (!text || typeof text !== 'string') return false;
    return /<[a-zA-Z][^>]*>/.test(text);
}

// Run stripHtml tests
console.log('Running stripHtml function tests...\n');

let passed = 0;
let failed = 0;

stripHtmlTests.forEach((test, index) => {
    const result = stripHtml(test.input);
    const isEqual = JSON.stringify(result) === JSON.stringify(test.expected);

    if (isEqual) {
        console.log(`✓ Test ${index + 1}: ${test.name}`);
        passed++;
    } else {
        console.log(`✗ Test ${index + 1}: ${test.name}`);
        console.log(`  Input: ${JSON.stringify(test.input)}`);
        console.log(`  Expected: ${JSON.stringify(test.expected)}`);
        console.log(`  Got: ${JSON.stringify(result)}`);
        failed++;
    }
});

console.log('\n---\nRunning API response sanitization tests...\n');

apiResponseTests.forEach((test, index) => {
    const rawValue = test.rawResponse[test.field]?.value || test.rawResponse[test.field];
    const cleanedValue = stripHtml(rawValue);

    const hasNoHtml = !containsHtmlTags(cleanedValue);
    const matchesExpected = cleanedValue === test.expectedClean;

    if (hasNoHtml && matchesExpected) {
        console.log(`✓ API Test ${index + 1}: ${test.name}`);
        passed++;
    } else {
        console.log(`✗ API Test ${index + 1}: ${test.name}`);
        console.log(`  Source: ${test.source}`);
        console.log(`  Raw: ${JSON.stringify(rawValue)}`);
        console.log(`  Cleaned: ${JSON.stringify(cleanedValue)}`);
        console.log(`  Expected: ${JSON.stringify(test.expectedClean)}`);
        if (containsHtmlTags(cleanedValue)) {
            console.log(`  ERROR: Result still contains HTML tags!`);
        }
        failed++;
    }
});

console.log('\n---\nHTML tag detection tests...\n');

const htmlDetectionTests = [
    { text: 'Plain text', shouldHaveHtml: false },
    { text: '<div>Has HTML</div>', shouldHaveHtml: true },
    { text: '5 > 3', shouldHaveHtml: false },
    { text: '<a href="">Link</a>', shouldHaveHtml: true },
    { text: '<br/>', shouldHaveHtml: true },
    { text: 'No tags here < but > symbols', shouldHaveHtml: false }
];

htmlDetectionTests.forEach((test, index) => {
    const hasHtml = containsHtmlTags(test.text);
    const isCorrect = hasHtml === test.shouldHaveHtml;

    if (isCorrect) {
        console.log(`✓ Detection Test ${index + 1}: "${test.text.substring(0, 30)}..." - ${test.shouldHaveHtml ? 'has HTML' : 'no HTML'}`);
        passed++;
    } else {
        console.log(`✗ Detection Test ${index + 1}: "${test.text}"`);
        console.log(`  Expected hasHtml=${test.shouldHaveHtml}, got ${hasHtml}`);
        failed++;
    }
});

console.log(`\n${'='.repeat(50)}`);
console.log(`${passed}/${passed + failed} tests passed`);

if (failed > 0) {
    process.exit(1);
}
