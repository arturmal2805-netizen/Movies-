import test from 'node:test';
import assert from 'node:assert/strict';
import {validatedCriticsScore,validatedImdbMetrics,hasVerifiedGenre} from './imdb-audience.js';
import {criticsBonus,isEligibleForSelection} from './audience-priority.js';
import {productionExclusion} from './production-policy.js';
import {filmCategories} from './categories.js';
const evidence={imdbId:'tt1234567',imdbVerified:true,imdbGenres:['Horror'],imdbYear:2020,metascore:78};
test('verified critic evidence never invents audience values and is bounded',()=>{
 const film={year:2020,genreIds:[53],remoteMetrics:evidence};
 assert.equal(validatedImdbMetrics(film),null);assert.equal(validatedCriticsScore(film),78);assert.ok(criticsBonus(film)>0);
 for(const change of [{imdbVerified:false},{imdbId:'bad'},{metascore:'78'},{metascore:true},{metascore:101}])assert.equal(criticsBonus({...film,remoteMetrics:{...evidence,...change}}),0);
 assert.equal(criticsBonus({...film,imdb_id:'tt9999999'}),0);
});
test('explicit IMDb horror recovers thriller classification without changing raw TMDB genres',()=>{
 const film={year:2020,genreIds:[53],remoteMetrics:evidence};
 assert.equal(hasVerifiedGenre(film,'Horror'),true);assert.ok(filmCategories(film).includes('horror'));assert.equal(isEligibleForSelection(film),true);assert.deepEqual(film.genreIds,[53]);
 for(const genre of ['Comedy','Documentary','Animation','Family','Adult'])assert.ok(productionExclusion({...film,remoteMetrics:{...evidence,imdbGenres:['Horror',genre]}}));
 for(const change of [{year:1999},{productionCountries:['JP']},{originalLanguage:'ja'},{remoteMetrics:{...evidence,imdbYear:1990}}])assert.equal(isEligibleForSelection({...film,...change}),false);
 assert.equal(isEligibleForSelection({...film,remoteMetrics:{...evidence,imdbGenres:['Thriller']}}),false);
});
