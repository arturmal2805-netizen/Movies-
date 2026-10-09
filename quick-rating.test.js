import test from 'node:test';import assert from 'node:assert/strict';
import {worstRating,normalizeRating,ratingLabel,isArchived} from './ratings.js';
import {tasteSignal,isDocumentary} from './taste.js';
test('one-click rejection is the worst complete rating and survives normalization',()=>{
 const rating=worstRating();assert.equal(rating.plot,1);assert.equal(rating.cinematography,1);assert.equal(rating.impression,'dislike');assert.deepEqual(normalizeRating(rating),rating);assert.ok(isArchived(rating));assert.equal(ratingLabel(rating),'Полная хуйня');assert.equal(tasteSignal(rating),-1);assert.ok(tasteSignal(rating)<tasteSignal({impression:'dislike',plot:5,cinematography:5}));
});
test('documentaries are identified even when combined with horror or missing canonical genre IDs',()=>{
 assert.ok(isDocumentary({genreIds:[27,99]}));assert.ok(isDocumentary({genre:'Документальный'}));assert.ok(isDocumentary({genre:'Documentary'}));assert.equal(isDocumentary({genreIds:[27],genre:'Ужасы'}),false);
});
