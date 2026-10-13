function verifiedRemote(film){
 const r=film.remoteMetrics;if(!r||r.imdbVerified!==true||typeof r.imdbId!=='string'||!/^tt[0-9]{7,12}$/.test(r.imdbId))return null;
 const canonical=film.imdb_id??film.imdbId;return canonical&&canonical!==r.imdbId?null:r;
}
export function validatedImdbMetrics(film){
 const r=verifiedRemote(film);return r&&Number.isFinite(r.imdb)&&r.imdb>0&&r.imdb<=10&&Number.isSafeInteger(r.imdbVoteCount)&&r.imdbVoteCount>0&&r.imdbVoteCount<=1e10?{rating:r.imdb,votes:r.imdbVoteCount}:null;
}
export function validatedCriticsScore(film){const r=verifiedRemote(film);return r&&Number.isInteger(r.metascore)&&r.metascore>=0&&r.metascore<=100?r.metascore:null;}
export function hasVerifiedGenre(film,genre){const r=verifiedRemote(film);return Boolean(r&&Array.isArray(r.imdbGenres)&&r.imdbGenres.includes(genre));}
export function verifiedImdbYear(film){const r=verifiedRemote(film);return r&&Number.isInteger(r.imdbYear)?r.imdbYear:null;}
