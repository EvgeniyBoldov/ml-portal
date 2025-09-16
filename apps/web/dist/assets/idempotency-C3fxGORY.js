function t(){return typeof crypto<"u"&&"randomUUID"in crypto?crypto.randomUUID():"idem_"+Math.random().toString(36).slice(2)+Date.now().toString(36)}export{t as i};
