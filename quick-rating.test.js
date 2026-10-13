import test from 'node:test';import assert from 'node:assert/strict';
import {worstRating,bestRating,neutralRating,normalizeRating,ratingLabel,isArchived} from './ratings.js';
import {tasteSignal,isDocumentary} from './taste.js';
test('one-click rejection is an interest rejection and survives normalization',()=>{
 const rating=worstRating();assert.equal(rating.plot,undefined);assert.equal(rating.cinematography,undefined);assert.equal(rating.feedbackStage,'interest');assert.equal(rating.interestLevel,1);assert.equal(rating.impression,'dislike');assert.deepEqual(normalizeRating(rating),rating);assert.ok(isArchived(rating));assert.equal(ratingLabel(rating),'Полная хуйня');assert.equal(tasteSignal(rating),-1);assert.ok(tasteSignal(rating)<tasteSignal({impression:'dislike',plot:5,cinematography:5}));
});
test('documentaries are identified even when combined with horror or missing canonical genre IDs',()=>{
 assert.ok(isDocumentary({genreIds:[27,99]}));assert.ok(isDocumentary({genre:'Документальный'}));assert.ok(isDocumentary({genre:'Documentary'}));assert.equal(isDocumentary({genreIds:[27],genre:'Ужасы'}),false);
});

test('one-click praise is the strongest positive signal, saved in archive and favorites',()=>{
 const rating=bestRating();assert.equal(rating.plot,undefined);assert.equal(rating.cinematography,undefined);assert.equal(rating.feedbackStage,'interest');assert.equal(rating.interestLevel,10);assert.equal(rating.impression,'like');assert.deepEqual(normalizeRating(rating),rating);assert.ok(isArchived(rating));assert.equal(ratingLabel(rating),'Самый разъёб');assert.equal(tasteSignal(rating),1);assert.ok(tasteSignal(rating)>tasteSignal({impression:'like',plot:5,cinematography:5}));
});

test('quick neutral saves interest level five and archives without becoming a favorite',()=>{const r=neutralRating();assert.equal(r.plot,undefined);assert.equal(r.cinematography,undefined);assert.equal(r.interestLevel,5);assert.equal(r.impression,'neutral');assert.ok(isArchived(r));assert.deepEqual(normalizeRating(r),r);assert.equal(ratingLabel(r),'Норм');});

test('card feedback cannot masquerade as a viewed film technical review',()=>{
 const normalized=normalizeRating({feedbackStage:'interest',impression:'dislike',interestLevel:1,plot:1,cinematography:1});
 assert.equal(normalized.plot,undefined);assert.equal(normalized.cinematography,undefined);
 assert.equal(tasteSignal({...normalized,plot:10,cinematography:10}),-1);
 const watched=normalizeRating({feedbackStage:'watched',impression:'dislike',plot:3,cinematography:4});
 assert.equal(watched.plot,3);assert.equal(watched.cinematography,4);
});
