/**
 * Unit tests for search ranking functionality.
 * Run with: node tests/test_search_ranking.js
 */

// Mock the getMatchScore function from app.js
function getMatchScore(item, query) {
    const name = item.n.toLowerCase();
    const tags = (item.t || []).map(t => t.toLowerCase());

    let score = 0;

    // Exact name match (highest priority)
    if (name === query) {
        score += 1000;
    }
    // Name starts with query
    else if (name.startsWith(query)) {
        score += 500;
    }
    // Name contains query as word (after colon/space)
    else if (name.includes(': ' + query) || name.endsWith(' ' + query) || name.includes(' ' + query + ' ')) {
        score += 350;
    }
    // Name contains query
    else if (name.includes(query)) {
        score += 100;
    }

    // Exact tag match (very important for short codes like "us", "de")
    if (tags.includes(query)) {
        score += 600;
    }
    // Tag starts with query
    else if (tags.some(t => t.startsWith(query))) {
        score += 250;
    }
    // Tag contains query
    else if (tags.some(t => t.includes(query))) {
        score += 50;
    }

    // Shorter names get a small boost
    score += Math.max(0, 30 - name.length);

    return score;
}

function rankResults(results, query) {
    return results.sort((a, b) => {
        const scoreA = getMatchScore(a, query);
        const scoreB = getMatchScore(b, query);
        return scoreB - scoreA;
    });
}

// Test data - simulating what would be in the search index
const testItems = [
    // US Flag - has "us" tag
    { id: 'us-flag', n: 'flag: United States', s: 'noto-emoji', t: ['emoji', 'flags', 'country-flag', 'us'] },
    // German Flag - has "de" tag
    { id: 'de-flag', n: 'flag: Germany', s: 'noto-emoji', t: ['emoji', 'flags', 'country-flag', 'de'] },
    // User icon - contains "us" in name
    { id: 'user', n: 'user', s: 'feather', t: ['icon', 'ui'] },
    { id: 'user-check', n: 'user-check', s: 'feather', t: ['icon', 'ui'] },
    { id: 'user-plus', n: 'user-plus', s: 'feather', t: ['icon', 'ui'] },
    { id: 'users', n: 'users', s: 'feather', t: ['icon', 'ui'] },
    // Items with "de" in name
    { id: 'delete', n: 'delete', s: 'feather', t: ['icon', 'ui'] },
    { id: 'code', n: 'code', s: 'feather', t: ['icon', 'ui'] },
    // Pause has "us" as substring
    { id: 'pause', n: 'pause', s: 'feather', t: ['icon', 'ui'] },
    // Focus has "us" as substring
    { id: 'focus', n: 'focus', s: 'feather', t: ['icon', 'ui'] },
    // Music has "us" as substring
    { id: 'music', n: 'music', s: 'feather', t: ['icon', 'ui'] },
    // Minus has "us" substring
    { id: 'minus', n: 'minus', s: 'feather', t: ['icon', 'ui'] },
];

// Test cases
const tests = [
    {
        name: 'Search "us" should rank US flag first',
        query: 'us',
        expectedFirst: 'us-flag',
        check: (results) => {
            const usFlag = results.find(r => r.id === 'us-flag');
            const firstResult = results[0];
            return {
                passed: firstResult.id === 'us-flag',
                message: `Expected first result to be 'us-flag', got '${firstResult.id}'. ` +
                         `US flag score: ${getMatchScore(usFlag, 'us')}, ` +
                         `First result score: ${getMatchScore(firstResult, 'us')}`
            };
        }
    },
    {
        name: 'Search "de" should rank German flag first',
        query: 'de',
        expectedFirst: 'de-flag',
        check: (results) => {
            const deFlag = results.find(r => r.id === 'de-flag');
            const firstResult = results[0];
            return {
                passed: firstResult.id === 'de-flag',
                message: `Expected first result to be 'de-flag', got '${firstResult.id}'. ` +
                         `DE flag score: ${getMatchScore(deFlag, 'de')}, ` +
                         `First result score: ${getMatchScore(firstResult, 'de')}`
            };
        }
    },
    {
        name: 'US flag should score higher than "user" for query "us"',
        query: 'us',
        check: (results) => {
            const usFlag = results.find(r => r.id === 'us-flag');
            const user = results.find(r => r.id === 'user');
            const usFlagScore = getMatchScore(usFlag, 'us');
            const userScore = getMatchScore(user, 'us');
            return {
                passed: usFlagScore > userScore,
                message: `US flag score (${usFlagScore}) should be > user score (${userScore})`
            };
        }
    },
    {
        name: 'German flag should score higher than "delete" for query "de"',
        query: 'de',
        check: (results) => {
            const deFlag = results.find(r => r.id === 'de-flag');
            const deleteIcon = results.find(r => r.id === 'delete');
            const deFlagScore = getMatchScore(deFlag, 'de');
            const deleteScore = getMatchScore(deleteIcon, 'de');
            return {
                passed: deFlagScore > deleteScore,
                message: `DE flag score (${deFlagScore}) should be > delete score (${deleteScore})`
            };
        }
    },
    {
        name: 'Exact tag match "us" should get score >= 600',
        query: 'us',
        check: (results) => {
            const usFlag = results.find(r => r.id === 'us-flag');
            const score = getMatchScore(usFlag, 'us');
            return {
                passed: score >= 600,
                message: `US flag score should be >= 600 (exact tag match), got ${score}`
            };
        }
    },
];

// Run tests
console.log('Running search ranking tests...\n');

let passed = 0;
let failed = 0;

tests.forEach((test, index) => {
    // Filter items that would match the query (simulating actual search)
    const matchingItems = testItems.filter(item => {
        const name = item.n.toLowerCase();
        const tags = (item.t || []).map(t => t.toLowerCase());
        const query = test.query.toLowerCase();
        return name.includes(query) || tags.some(t => t.includes(query) || t === query);
    });

    const results = rankResults([...matchingItems], test.query.toLowerCase());
    const result = test.check(results);

    if (result.passed) {
        console.log(`✓ Test ${index + 1}: ${test.name}`);
        passed++;
    } else {
        console.log(`✗ Test ${index + 1}: ${test.name}`);
        console.log(`  ${result.message}`);
        failed++;
    }
});

console.log(`\n${passed}/${passed + failed} tests passed`);

if (failed > 0) {
    process.exit(1);
}
